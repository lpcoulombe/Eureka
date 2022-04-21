import numpy as np
import george
from george import kernels
import celerite
from copy import deepcopy
from .Model import Model
from ...lib.readEPF import Parameters

###########for future tinygp version - tinygp needs python >= 3.7
###########!! careful when activating - did not test the tinygp code yet (didn't have python >= 3.7)
#import jax.numpy as jnp
#import tinygp
#from tinygp import kernels, GaussianProcess
#from jax.config import config
#config.update("jax_enable_x64", True)

class GPModel(Model):
    """Model for Gaussian Process (GP)"""
    def __init__(self, kernel_classes, kernel_inputs, lc, gp_code='george', **kwargs):
        """Initialize the GP model
        """
        # Inherit from Model class
        super().__init__(**kwargs)

        # Define model type (physical, systematic, other)
        self.modeltype = 'GP'
        
        #get GP parameters
        self.gp_code_name = gp_code
        self.kernel_types = kernel_classes
        self.kernel_input_names = kernel_inputs
        self.kernel_input_arrays = []
        self.nkernels = len(kernel_classes)
        self.flux = lc.flux
        self.unc_fit = lc.unc
        self.time = lc.time

        # Check for Parameters instance
        self.parameters = kwargs.get('parameters')

        # Generate parameters from kwargs if necessary
        if self.parameters is None:
            self.parameters = Parameters(**kwargs)
        
        # Set parameters for multi-channel fits
        self.longparamlist = kwargs.get('longparamlist')
        self.nchan = kwargs.get('nchan')
        self.paramtitles = kwargs.get('paramtitles')
        
        # Update coefficients
        self._parse_coeffs()
        

    def _parse_coeffs(self):
        """Convert dict of coefficients into a list
        of coefficients in increasing order

        Parameters
        ----------
        None

        Returns
        -------
        dictionary of coefficients for GP kernels
        """
        # Parse keyword arguments as coefficients
        self.coeffs = {}
        for i in range(self.nkernels):
            self.coeffs[self.kernel_types[i]]=[]
        for k, v in self.parameters.dict.items():
            if k.startswith('A'):
                remvisnum=k.split('_')
                if len(remvisnum)>1:
                    self.coeffs['A_%i'%int(remvisnum[1])]  = v[0]
                elif self.nchan > 1:
                    self.coeffs['A_0']  = v[0]
                else:
                    self.coeffs['A'] = v[0]
            if k.lower().startswith('m'):
                remvisnum=k.split('_')
                if len(remvisnum)>1 or self.nchan > 1:
                    no = int(remvisnum[0][1])-1
                    if no < 0:
                        raise AssertionError('Please start your metric enumeration with m1.')
                    self.coeffs[self.kernel_types[no]].append(v[0])
                else:
                    no = int(remvisnum[0][1])-1
                    self.coeffs[self.kernel_types[no]].append(v[0])
            if k.startswith('WN'):
                remvisnum = k.split('_')
                if len(remvisnum)>1:
                    self.coeffs['WN_%i'%int(remvisnum[1])] = v[0]
                elif self.nchan > 1:
                    self.coeffs['WN_0']  = v[0]
                else:
                    self.coeffs['WN'] = v[0]
                if 'fixed' in v:
                    self.fit_white_noise = False
                else:
                    self.fit_white_noise = True
                    
    
    def eval(self, fit, gp=None, **kwargs):
        """Compute GP with the given parameters
        Parameters 
        ----------
        fit - current model (i.e. transit model)

        Returns
        -------
        predicted systematics model 
        """
        lcfinal=np.array([])
        
        for c in np.arange(self.nchan):
            #get flux and uncertainties for current channel
            c_flux = self.flux[len(self.time)*c:len(self.time)*(c+1)]
            c_fit = fit[len(self.time)*c:len(self.time)*(c+1)]
            c_unc_fit = self.unc_fit[len(self.time)*c:len(self.time)*(c+1)]
            # Create the GP object with current parameters
            if gp==None:
                gp = self.setup_GP(c)       
            if self.nkernels > 1:
                if self.gp_code_name == 'george':
                    gp.compute(self.kernel_input_arrays.T,c_unc_fit)
                    mu,cov = gp.predict(c_flux- c_fit,self.kernel_input_arrays.T)
                if self.gp_code_name == 'tinygp':
                    cond_gp = gp.condition(self.kernel_input_arrays.T,c_unc_fit).gp
                    mu, cov = cond_gp.loc, cond_gp.variance
                if self.gp_code_name == 'celerite':
                    raise AssertionError('Celerite cannot compute multi-dimensional GPs, please choose a different GP code')
            else:
                if self.gp_code_name == 'george':
                    gp.compute(self.kernel_input_arrays[0],c_unc_fit)
                    mu,cov = gp.predict(c_flux- c_fit,self.kernel_input_arrays[0])
                if self.gp_code_name == 'tinygp':
                    cond_gp = gp.condition(self.kernel_inputs[0],c_unc_fit).gp
                    mu, cov = cond_gp.loc, cond_gp.variance
                if self.gp_code_name == 'celerite':
                    gp.compute(self.kernel_input_arrays[0], c_unc_fit)
                    mu, cov = gp.predict(c_flux- c_fit, self.kernel_input_arrays[0], return_var=True)
                    mu += gp.kernel.jitter*np.ones(len(c_flux))
            lcfinal = np.append(lcfinal, mu)

        return lcfinal#, cov

    def set_inputs(self, normalise=False):
        """Setting up kernel inputs as array and standardizing them 
        see e.g. Evans et al. 2017
        Parameters
        ----------
        kernel input as strings e.g. 'time' 

        Returns
        ----------
        kernel inputs as a np.array
        """
        kernel_inputs = []
        for i in self.kernel_input_names:
            if i == 'time':
                x = self.time
                #x = np.linspace(0.10, 0.22, num=1287)
                kernel_inputs.append(x)
                #kernel_inputs.append(self.time)
            ##add more input options here 

        if normalise: 
            #print(kernel_inputs)
            norm_kernel_inputs = [(i-i.mean())/i.std() for i in kernel_inputs]
            self.kernel_input_arrays =  np.array(norm_kernel_inputs)
            return
        else:
            self.kernel_input_arrays = np.array(kernel_inputs)
        return

    def setup_GP(self,channel, **kwargs):
        """Set up GP kernels and GP object.
        
        Parameters
        ----------
        None

        Returns
        -------
        GP object

        """
        
        
        if len(self.kernel_input_arrays) == 0:
            self.set_inputs()
        
        if self.nchan > 1:
            for i in range(self.nkernels):
                if i == 0:
                    kernel = self.get_kernel(self.kernel_types[i],i, channel)
                else:
                    kernel += self.get_kernel(self.kernel_types[i],i, channel)

            if self.gp_code_name == 'celerite':
                kernel = celerite.terms.RealTerm(log_a = self.coeffs['A_%i'%channel], log_c = 0)*kernel
                kernel += celerite.terms.JitterTerm(log_sigma = self.coeffs['WN_%i'%channel])
                gp = celerite.GP(kernel, mean=0, fit_mean=False)

            if self.gp_code_name == 'george':
                kernel = kernels.ConstantKernel(self.coeffs['A_%i'%channel],ndim=self.nkernels,axes=np.arange(self.nkernels))*kernel
                gp = george.GP(kernel, white_noise=self.coeffs['WN_%i'%channel],fit_white_noise=self.fit_white_noise, mean=0, fit_mean=False)#, solver=george.solvers.HODLRSolver)

            if self.gp_code_name == 'tinygp':
                kernel = kernels.ConstantKernel(self.coeffs['A_%i'%channel],ndim=self.nkernels,axes=np.arange(self.nkernels))*kernel
                gp = tinygp.GaussianProcess(kernel, diag=self.coeffs['WN_%i'%channel]**2, mean=0)
                
        else:
            for i in range(self.nkernels):
                if i == 0:
                    kernel = self.get_kernel(self.kernel_types[i],i)
                else:
                    kernel += self.get_kernel(self.kernel_types[i],i)

            if self.gp_code_name == 'celerite':
                kernel = celerite.terms.RealTerm(log_a = self.coeffs['A'], log_c = 0)*kernel
                kernel += celerite.terms.JitterTerm(log_sigma = self.coeffs['WN'])
                gp = celerite.GP(kernel, mean=0, fit_mean=False)

            if self.gp_code_name == 'george':
                kernel = kernels.ConstantKernel(self.coeffs['A'],ndim=self.nkernels,axes=np.arange(self.nkernels))*kernel
                gp = george.GP(kernel, white_noise=self.coeffs['WN'],fit_white_noise=self.fit_white_noise, mean=0, fit_mean=False)#, solver=george.solvers.HODLRSolver)

            if self.gp_code_name == 'tinygp':
                kernel = kernels.ConstantKernel(self.coeffs['A'],ndim=self.nkernels,axes=np.arange(self.nkernels))*kernel
                gp = tinygp.GaussianProcess(kernel, diag=self.coeffs['WN']**2, mean=0)

        return gp

    def loglikelihood(self, fit, unc_fit):
        """Compute log likelihood of GP
        Parameters 
        ----------
        None

        Returns
        -------
        log likelihood of the GP evaluated by george/tinygp
        """
        #update uncertainty
        self.unc_fit = unc_fit

        logL = []
        
        for c in np.arange(self.nchan):
            gp = self.setup_GP(c)
            c_flux = self.flux[len(self.time)*c:len(self.time)*(c+1)]
            c_fit = fit[len(self.time)*c:len(self.time)*(c+1)]
            c_unc_fit = self.unc_fit[len(self.time)*c:len(self.time)*(c+1)]
        
            if self.gp_code_name == 'celerite':
                if self.nkernels > 1:
                    raise AssertionError('Celerite cannot compute multi-dimensional GPs, please choose a different GP code')
                else:
                    gp.compute(self.kernel_input_arrays[0], c_unc_fit)
                logL.append(gp.log_likelihood(c_flux - c_fit))

            if self.gp_code_name == 'george':
                if self.nkernels > 1:
                    gp.compute(self.kernel_input_arrays.T,c_unc_fit)
                else:
                    gp.compute(self.kernel_input_arrays[0],c_unc_fit)
                logL.append(gp.lnlikelihood(c_flux - c_fit,quiet=True))

            if self.gp_code_name == 'tinygp':
                if self.nkernels > 1:
                    logL.append(gp.condition(c_flux - c_fit, X_test = self.kernel_input_arrays.T).log_probability)
                else:
                    logL.append(gp.condition(c_flux - c_fit, X_test = self.kernel_input_arrays[0]).log_probability) 
                    
        return sum(logL)

    def get_kernel(self, kernel_name, i, channel=0):
        """get individual kernels"""
        metric = ( 1./np.exp(self.coeffs[kernel_name][channel]) )**2
        if self.gp_code_name == 'george':
            if kernel_name == 'Matern32':
                kernel = kernels.Matern32Kernel(metric,ndim=self.nkernels,axes=i)
            if kernel_name == 'ExpSquared':
                kernel = kernels.ExpSquaredKernel(metric,ndim=self.nkernels,axes=i)
            if kernel_name == 'RationalQuadratic':
                kernel = kernels.RationalQuadraticKernel(log_alpha=1,metric=metric,ndim=self.nkernels,axes=i)
            if kernel_name == 'Exp':
                kernel = kernels.ExpKernel(metric,ndim=self.nkernels,axes=i)   

        if self.gp_code_name == 'tinygp':
            if kernel_name == 'Matern32':
                kernel = tinygp.kernels.Matern32(metric,ndim=self.nkernels,axes=i)
            if kernel_name == 'ExpSquared':
                kernel = tinygp.kernels.ExpSquared(metric,ndim=self.nkernels,axes=i)
            if kernel_name == 'RationalQuadratic':
                kernel = tinygp.kernels.RationalQuadratic(alpha=1,scale=metric,ndim=self.nkernels,axes=i)
            if kernel_name == 'Exp':
                kernel = tinygp.kernels.Exp(metric,ndim=self.nkernels,axes=i) 
                
        if self.gp_code_name == 'celerite':
            if kernel_name == 'Matern32':
                kernel = celerite.terms.Matern32Term(log_sigma = 1, log_rho = metric)
            else:
                raise AssertionError('Celerite currently only supports a Matern32 kernel')

        return kernel

    def update(self, newparams, names, **kwargs):
        """Update parameter values"""
        for ii,arg in enumerate(names):
            if hasattr(self.parameters,arg):
                val = getattr(self.parameters,arg).values[1:]
                val[0] = newparams[ii]
                setattr(self.parameters, arg, val)
        self._parse_coeffs()
        return