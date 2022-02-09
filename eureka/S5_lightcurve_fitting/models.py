"""Base and child classes to handle models
used to fit light curves

Author: Joe Filippazzo
Email: jfilippazzo@stsci.edu
"""
import numpy as np
import matplotlib.pyplot as plt
import copy
import inspect
import os

import astropy.units as q
try:
    import batman
except ImportError:
    print("Could not import batman. Functionality may be limited.")
#from bokeh.plotting import figure, show

from .parameters import Parameters
from .utils import COLORS
from .limb_darkening_fit import ld_profile
import pdb

class Model:
    def __init__(self, **kwargs):
        """
        Create a model instance
        """
        # Set up model attributes
        self.name = 'New Model'
        self.fitter = None
        self._time = None
        self._flux = None
        self._units = q.day
        self._parameters = Parameters()
        self.components = None
        self.fmt = None

        # Store the arguments as attributes
        for arg, val in kwargs.items():
            setattr(self, arg, val)

    def __mul__(self, other):
        """Multiply model components to make a combined model

        Parameters
        ----------
        other: ExoCTK.lightcurve_fitting.models.Model
            The model to multiply

        Returns
        -------
        ExoCTK.lightcurve_fitting.lightcurve.Model
            The combined model
        """
        # Make sure it is the right type
        attrs = ['units', 'flux', 'time']
        if not all([hasattr(other, attr) for attr in attrs]):
            raise TypeError('Only another Model instance may be multiplied.')

        # Combine the model parameters too
        params = self.parameters + other.parameters

        return CompositeModel([copy.copy(self), other], parameters=params)

    @property
    def flux(self):
        """A getter for the flux"""
        return self._flux

    @flux.setter
    def flux(self, flux_array):
        """A setter for the flux

        Parameters
        ----------
        flux_array: sequence
            The flux array
        """
        # Check the type
        if not isinstance(flux_array, (np.ndarray, tuple, list)):
            raise TypeError("flux axis must be a tuple, list, or numpy array.")

        # Set the array
        self._flux = np.array(flux_array)

    def interp(self, new_time):
        """Interpolate the flux to a new time axis

        Parameters
        ----------
        new_time: sequence, astropy.units.quantity.Quantity
            The time array
        """
        # Check the type
        if not isinstance(new_time, (np.ndarray, tuple, list)):
            raise TypeError("Time axis must be a tuple, list, or numpy array")

        # Calculate the new flux
        self.flux = np.interp(new_time, self.time, self.flux)

        # Set the new time axis
        self.time = new_time

    @property
    def parameters(self):
        """A getter for the parameters"""
        return self._parameters

    @parameters.setter
    def parameters(self, params):
        """A setter for the parameters"""
        # Process if it is a parameters file
        if isinstance(params, str) and os.file.exists(params):
            params = Parameters(params)

        # Or a Parameters instance
        if not isinstance(params, (Parameters, type(None))):
            raise TypeError("'params' argument must be a JSON file, ascii\
                             file, or parameters.Parameters instance.")

        # Set the parameters attribute
        self._parameters = params

    def plot(self, time, components=False, ax=None, draw=False, color='blue', zorder=np.inf, share=False, nchan=0, **kwargs):
        """Plot the model

        Parameters
        ----------
        time: array-like
            The time axis to use
        components: bool
            Plot all model components
        ax: Matplotlib Axes
            The figure axes to plot on

        Returns
        -------
        bokeh.plotting.figure
            The figure
        """
        # Make the figure

        if share:
            for channel in np.arange(nchan):
                if ax is None:
                    fig = plt.figure(figsize=(8,6))
                    ax = fig.gca()

                # Set the time
                self.time = time

                # Plot the model
                label = self.fitter
                if self.name!='New Model':
                    label += ': '+self.name
                ax.plot(self.time, self.eval(**kwargs), '-', label=label, color=color, zorder=zorder)

                if components and self.components is not None:
                    for comp in self.components:
                        comp.plot(self.time, ax=ax, draw=False, color=next(COLORS), zorder=zorder, label=comp.fitter+': '+comp.name, **kwargs)

                # Format axes
                ax.set_xlabel(str(self.time_units))
                ax.set_ylabel('Flux')

                if draw:
                    fig.show()
            return
        else:
            if ax is None:
                fig = plt.figure(figsize=(8,6))
                ax = fig.gca()

            # Set the time
            self.time = time

            # Plot the model
            label = self.fitter
            if self.name!='New Model':
                label += ': '+self.name
            ax.plot(self.time, self.eval(**kwargs), '-', label=label, color=color, zorder=zorder)

            if components and self.components is not None:
                for comp in self.components:
                    comp.plot(self.time, ax=ax, draw=False, color=next(COLORS), zorder=zorder, label=comp.fitter+': '+comp.name, **kwargs)

            # Format axes
            ax.set_xlabel(str(self.time_units))
            ax.set_ylabel('Flux')

            if draw:
                fig.show()
            else:
                return

    @property
    def time(self):
        """A getter for the time"""
        return self._time

    @time.setter
    def time(self, time_array, time_units='BJD'):
        """A setter for the time

        Parameters
        ----------
        time_array: sequence, astropy.units.quantity.Quantity
            The time array
        time_units: str
            The units of the input time_array, ['MJD', 'BJD', 'phase']
        """
        # Check the type
        if not isinstance(time_array, (np.ndarray, tuple, list)):
            raise TypeError("Time axis must be a tuple, list, or numpy array.")

        # Set the units
        self.time_units = time_units

        # Set the array
        self._time = time_array

    @property
    def units(self):
        """A getter for the units"""
        return self._units

    @units.setter
    def units(self, units):
        """A setter for the units

        Parameters
        ----------
        units: str
            The time units ['BJD', 'MJD', 'phase']
        """
        # Check the type
        if units not in ['BJD', 'MJD', 'phase']:
            raise TypeError("units axis must be 'BJD', 'MJD', or 'phase'.")

        self._units = units


class CompositeModel(Model):
    """A class to create composite models"""
    def __init__(self, models, **kwargs):
        """Initialize the composite model

        Parameters
        ----------
        models: sequence
            The list of models
        """
        # Inherit from Model calss
        super().__init__(**kwargs)

        # Store the models
        self.components = models

    def eval(self, **kwargs):
        """Evaluate the model components"""
        # Get the time
        if self.time is None:
            self.time = kwargs.get('time')

        # Empty flux
        flux = 1.

        # Evaluate flux at each model
        for model in self.components:
            if model.time is None:
                model.time = self.time
            flux *= model.eval(**kwargs)

        return flux

    def update(self, newparams, names, **kwargs):
        """Update parameters in the model components"""
        # Evaluate flux at each model
        for model in self.components:
            model.update(newparams, names, **kwargs)

        return


class PolynomialModel(Model):
    """Polynomial Model"""
    def __init__(self, **kwargs):
        """Initialize the polynomial model
        """
        # Inherit from Model class
        super().__init__(**kwargs)

        # Check for Parameters instance
        self.parameters = kwargs.get('parameters')

        # Generate parameters from kwargs if necessary
        if self.parameters is None:
            coeff_dict = kwargs.get('coeff_dict')
            params = {cN: coeff for cN, coeff in coeff_dict.items()
                      if cN.startswith('c') and cN[1:].isdigit()}
            self.parameters = Parameters(**params)

        # Set whether the fit is shared or not
        self.share = kwargs.get('share')
        self.longparamlist = kwargs.get('longparamlist')
        self.nchan = kwargs.get('nchan')
        self.chan = kwargs.get('chan')

        if self.share is None:
            self.share = False
        
        # Update coefficients
        self._parse_coeffs()
        
    def _parse_coeffs(self, **kwargs):
        """Convert dict of 'c#' coefficients into a list
        of coefficients in decreasing order, i.e. ['c2','c1','c0']

        Parameters
        ----------
        None

        Returns
        -------
        np.ndarray
            The sequence of coefficient values
        """

        # Parse 'c#' keyword arguments as coefficients
        coeffs = np.zeros((self.nchan,9))
        for k, v in self.parameters.dict.items():
            remvisnum=k.split('_')
            if k.lower().startswith('c') and k[1:].isdigit():
                coeffs[0,int(k[1:])] = v[0]
            elif len(remvisnum)>1:
                if remvisnum[0].lower().startswith('c') and remvisnum[0][1:].isdigit() and remvisnum[1].isdigit():
                    coeffs[int(remvisnum[1]),int(remvisnum[0][1:])] = v[0]

        # Trim zeros and reverse
        coeffs=coeffs[:,~np.all(coeffs==0,axis=0)]
        coeffs=np.flip(coeffs,axis=1)
        self.coeffs=coeffs
        # self.coeffs = np.trim_zeros(coeffs)[::-1]

    def eval(self, **kwargs):
        """Evaluate the function with the given values"""
        # Get the time
        if self.time is None:
            self.time = kwargs.get('time')

        longparamlist=self.longparamlist
        nchan=self.nchan
        paramtitles=longparamlist[0]

        # Convert to local time
        time_local = self.time - self.time.mean()

        # Create the polynomial from the coeffs
        if self.share:
            lcfinal=np.array([])
            for c in np.arange(nchan):
                poly = np.poly1d(self.coeffs[c])
                lcpiece = np.polyval(poly, time_local)
                lcfinal = np.append(lcfinal, lcpiece)
            return lcfinal

        else:
            poly = np.poly1d(self.coeffs[self.chan])
            return np.polyval(poly, time_local)

    def update(self, newparams, names, **kwargs):
        """Update parameter values"""
        for ii,arg in enumerate(names):
            if hasattr(self.parameters,arg):
                val = getattr(self.parameters,arg).values[1:]
                val[0] = newparams[ii]
                setattr(self.parameters, arg, val)
        self._parse_coeffs()
        return

class TransitModel(Model):
    """Transit Model"""
    def __init__(self, **kwargs):
        """Initialize the transit model
        """
        # Inherit from Model calss
        super().__init__(**kwargs)

        # Check for Parameters instance
        self.parameters = kwargs.get('parameters')

        # Generate parameters from kwargs if necessary
        if self.parameters is None:
            self.parameters = Parameters(**kwargs)
        
        # Set whether the fit is shared or not
        self.share = kwargs.get('share')
        self.longparamlist = kwargs.get('longparamlist')
        self.nchan = kwargs.get('nchan')
        self.chan = kwargs.get('chan')

        if self.share is None:
            self.share = False

        # Store the ld_profile
        self.ld_func = ld_profile(self.parameters.limb_dark.value)
        len_params = len(inspect.signature(self.ld_func).parameters)
        self.coeffs = ['u{}'.format(n) for n in range(len_params)[1:]]

    def eval(self, **kwargs):
        """Evaluate the function with the given values"""
        # Get the time
        if self.time is None:
            self.time = kwargs.get('time')
              
        longparamlist=self.longparamlist
        nchan=self.nchan
        paramtitles=longparamlist[0]

        # Set all parameters
        if self.share:
            lcfinal=np.array([])
            for c in np.arange(nchan):
                m_eclipse = batman_lc(self.time,paramtitles,longparamlist[c],self.parameters,self.coeffs)
                lcfinal = np.append(lcfinal,m_eclipse)

            return lcfinal

        else:
            m_eclipse = batman_lc(self.time,paramtitles,longparamlist[self.chan],self.parameters,self.coeffs)
            return m_eclipse

    def update(self, newparams, names, **kwargs):
        """Update parameter values"""
        for ii,arg in enumerate(names):
            if hasattr(self.parameters,arg):
                val = getattr(self.parameters,arg).values[1:]
                val[0] = newparams[ii]
                setattr(self.parameters, arg, val)
        return

class ExponentialModel(Model):
    """Model for single or double exponential ramps"""
    def __init__(self, **kwargs):
        """Initialize the exponential ramp model
        """
        # Inherit from Model calss
        super().__init__(**kwargs)

        # Check for Parameters instance
        self.parameters = kwargs.get('parameters')

        # Generate parameters from kwargs if necessary
        if self.parameters is None:
            self._parse_coeffs(kwargs)

    def _parse_coeffs(self, coeff_dict):
        """Convert dict of 'r#' coefficients into a list
        of coefficients in increasing order, i.e. ['r0','r1','r2']

        Parameters
        ----------
        coeff_dict: dict
            The dictionary of coefficients

        Returns
        -------
        np.ndarray
            The sequence of coefficient values
        """
        params = {rN: coeff for rN, coeff in coeff_dict.items()
                  if rN.startswith('r') and rN[1:].isdigit()}
        self.parameters = Parameters(**params)

        # Parse 'c#' keyword arguments as coefficients
        coeffs = np.zeros(100)
        for k, v in self.parameters.dict.items():
            if k.lower().startswith('r') and k[1:].isdigit():
                coeffs[int(k[1:])] = v[0]

        # Trim zeros and reverse
        self.coeffs = np.trim_zeros(coeffs)

    def eval(self, **kwargs):
        """Evaluate the function with the given values"""
        # Get the time
        if self.time is None:
            self.time = kwargs.get('time')

        # Create the individual coeffs
        if len(self.coeffs) == 3:
            r0, r1, r2 = self.coeffs
            r3, r4, r5 = 0, 0, 0
        elif len(self.coeffs) == 6:
            r0, r1, r2, r3, r4, r5 = self.coeffs
        else:
            raise IndexError('Exponential ramp requires 3 or 6 parameters labelled r#.')

        # Convert to local time
        time_local = self.time - self.time.mean()

        # Evaluate the polynomial
        return r0*np.exp(-r1*time_local + r2) + r3*np.exp(-r4*time_local + r5) + 1

    def update(self, newparams, names, **kwargs):
        """Update parameter values"""
        for ii,arg in enumerate(names):
            val = getattr(self.parameters,arg).values[1:]
            val[0] = newparams[ii]
            setattr(self.parameters, arg, val)
        return

def batman_lc(time,paramtitles,paramvals,parameters,coeffs):
    #Initialize model
    bm_params = batman.TransitParams()

    # Set all parameters
    for index,item in enumerate(paramvals):
        setattr(bm_params,paramtitles[index],parameters.dict[item][0])

    # Combine limb darkening coeffs
    bm_params.u = [getattr(parameters, u).value for u in coeffs]

    # Use batman ld_profile name
    if parameters.limb_dark.value == '4-parameter':
        bm_params.limb_dark = 'nonlinear'

    # Make the eclipse
    tt = parameters.transittype.value
    m_eclipse = batman.TransitModel(bm_params, time, transittype=tt)

    return m_eclipse.light_curve(bm_params)

