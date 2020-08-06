# -*- coding: utf-8 -*-
import joblib
import numpy as np
from astropy import constants
from matplotlib import pyplot as plt
from scipy.optimize import minimize

SOL_kms = constants.c.value / 1000


# sine bell curves
def sinebell(n=1000, index=0.5):
    """ sine bell to left & right end of spectra """
    return np.sin(np.linspace(0, np.pi, n)) ** index


def sinebell_like(x, index=0.5):
    return sinebell(len(x), index=index)


def test_sinebell():
    plt.figure()
    plt.plot(sinebell(4000, 1))
    plt.plot(sinebell(4000, 1 / 2))
    plt.plot(sinebell(4000, 1 / 3))
    return


def test_sinebell2():
    """ load data """
    wave, flux, flux_err = np.loadtxt('/hydrogen/projects/song/delCep_order20.dat').T
    # flux_sine = flux - flux.mean()
    flux_sine = 1 - flux
    flux_sine = flux_sine * sinebell_like(flux, 1.0)

    plt.figure()
    plt.plot(wave, (flux - 1))
    plt.plot(wave, flux_sine)
    # plot(wave, flux_err)
    return wave, flux_sine


# CCF related functions
def wmean(x, w=None):
    """ weighted mean """
    if w is None:
        return np.mean(x)
    else:
        return np.sum(x * w) / np.sum(w)


def wcov(x1, x2, w=None):
    """ weighted covariance """
    return wmean((x1 - wmean(x1, w)) * (x2 - wmean(x2, w)), w)


def wxcorr(x1, x2, w=None):
    """ weighted cross-correlation """
    return wcov(x1, x2, w) / np.sqrt(wcov(x1, x1, w) * wcov(x2, x2, w))


def wxcorr_spec(rv, wave_obs, flux_obs, wave_mod, flux_mod, w_mod=None, w_obs=None):
    """ weighted cross correlation of two spectra"""
    if w_mod is None and w_obs is None:
        flux_mod_interp = np.interp(wave_obs, wave_mod * (1 + rv / SOL_kms), flux_mod)
        return wxcorr(flux_obs, flux_mod_interp, w=None)
    elif w_mod is None and w_obs is not None:
        flux_mod_interp = np.interp(wave_obs, wave_mod * (1 + rv / SOL_kms), flux_mod)
        return wxcorr(flux_obs, flux_mod_interp, w=w_obs)
    elif w_mod is not None and w_obs is None:
        flux_mod_interp = np.interp(wave_obs, wave_mod * (1 + rv / SOL_kms), flux_mod)
        w_mod_interp = np.interp(wave_obs, wave_mod * (1 + rv / SOL_kms), w_mod)
        return wxcorr(flux_obs, flux_mod_interp, w=w_mod_interp)
    else:
        flux_mod_interp = np.interp(wave_obs, wave_mod * (1 + rv / SOL_kms), flux_mod)
        w_mod_interp = np.interp(wave_obs, wave_mod * (1 + rv / SOL_kms), w_mod)
        return wxcorr(flux_obs, flux_mod_interp, w=w_mod_interp * w_obs)


def wxcorr_spec_cost(rv, wave_obs, flux_obs, wave_mod, flux_mod, w_mod=None, w_obs=None):
    """ the negative of wxcorr_spec, used as cost function for minimiztion """
    return - wxcorr_spec(rv, wave_obs, flux_obs, wave_mod, flux_mod, w_mod, w_obs)


def wxcorr_spec_binary(rv1, drv, eta, wave_obs, flux_obs, wave_mod, flux_mod, w_obs=None):
    """ weighted cross correlation of two spectra
    Note
    ----
    w_mod is not supported in this case
    """
    flux_mod_interp = np.interp(wave_obs, wave_mod * (1 + rv1 / SOL_kms), flux_mod) + \
                      eta * np.interp(wave_obs, wave_mod * (1 + (rv1 + drv) / SOL_kms), flux_mod)
    return wxcorr(flux_obs, flux_mod_interp, w=w_obs)


def wxcorr_spec_cost_binary(rv1_drv_eta, wave_obs, flux_obs, wave_mod, flux_mod, w_obs=None, eta_lim=(0.1, 1.2)):
    """ the negative of wxcorr_spec, used as cost function for minimiztion """
    rv1, drv, eta = rv1_drv_eta
    if not eta_lim[0] < eta <= eta_lim[1]:
        return np.inf
    return - wxcorr_spec_binary(rv1, drv, eta, wave_obs, flux_obs, wave_mod, flux_mod, w_obs=w_obs)


def wxcorr_rvgrid_binary(wave_obs, flux_obs, wave_mod, flux_mod,
                         rv1_init=0, eta_init=0.3, eta_lim=(0.1, 1.2),
                         drvmax=500, drvstep=5, w_obs=None, method="Powell"):
    # make grid
    drv_grid = np.arange(-drvmax, drvmax, drvstep)

    # ccf2_grid
    ccf2_grid = np.zeros_like(drv_grid, float)
    for idrv, drv in enumerate(drv_grid):
        ccf2_grid[idrv] = wxcorr_spec_binary(
            rv1_init, drv, eta_init, wave_obs, flux_obs, wave_mod, flux_mod, w_obs=w_obs)

    # find grid best
    drv_best = drv_grid[np.argmax(ccf2_grid)]
    x0 = np.array([rv1_init, drv_best, eta_init])

    # optimization
    opt = minimize(wxcorr_spec_cost_binary, x0, method=method, args=(wave_obs, flux_obs, wave_mod, flux_mod, w_obs, eta_lim))
    opt["x0"] = x0
    opt["ccfmax2"] = -opt["fun"]

    return opt


def respw_cost(rv, wave_obs, flux_obs, wave_mod, flux_mod, pw=1):
    flux_mod_interp = np.interp(wave_obs, wave_mod * (1 + rv / SOL_kms), flux_mod)
    cost = np.sum(np.abs(flux_obs - flux_mod_interp) ** pw)
    return cost


def respw_rvgrid(wave_obs, flux_obs, wave_mod, flux_mod, pw=1, rv_grid=np.arange(-500, 510, 10)):
    respw_grid = np.array([respw_cost(rv, wave_obs, flux_obs, wave_mod, flux_mod, pw=pw) for rv in rv_grid])
    return respw_grid


def wxcorr_rvgrid(wave_obs, flux_obs, wave_mod, flux_mod, rv_grid=np.arange(-500, 510, 10),
                  w_mod=None, w_obs=None):
    """ weighted cross-correlation method
    Interpolate a model spectrum with different RV and cross-correlate with
    the observed spectrum, return the CCF on the RV grid.

    wave_obs: array
        wavelength of observed spectrum (normalized)
    flux_obs: array
        flux of observed spectrum
    wave_mod: array
        wavelength of model spectrum (normalized)
    flux_mod:
        flux of model spectrum
    mask_obs:
        True for bad pixels
    rv_grid:
        km/s RV grid

    """
    wave_obs = np.asarray(wave_obs)
    flux_obs = np.asarray(flux_obs)
    wave_mod = np.asarray(wave_mod)
    flux_mod = np.asarray(flux_mod)

    # RV grid --> CCF grid
    rv_grid = np.asarray(rv_grid)
    # nz = len(z_grid)
    ccf_grid = np.ones_like(rv_grid, float)

    # calculate WCCF
    for i_rv, this_rv in enumerate(rv_grid):
        ccf_grid[i_rv] = wxcorr_spec(this_rv, wave_obs, flux_obs, wave_mod, flux_mod, w_mod, w_obs)

    return rv_grid, ccf_grid


def xcorr_rvgrid(wave_obs, flux_obs, wave_mod, flux_mod, mask_obs=None, rv_grid=np.arange(-500, 510, 10)):
    """ a naive cross-correlation method
    Interpolate a model spectrum with different RV and cross-correlate with
    the observed spectrum, return the CCF on the RV grid.
    
    wave_obs: array
        wavelength of observed spectrum (normalized)
    flux_obs: array
        flux of observed spectrum
    wave_mod: array
        wavelength of model spectrum (normalized)
    flux_mod:
        flux of model spectrum
    mask_obs:
        True for bad pixels
    rv_grid:
        km/s RV grid
    
    """
    wave_obs = np.asarray(wave_obs)
    flux_obs = np.asarray(flux_obs)
    wave_mod = np.asarray(wave_mod)
    flux_mod = np.asarray(flux_mod)

    if mask_obs is None:
        mask_obs = np.logical_not(np.isfinite(flux_obs))
    else:
        mask_obs = np.asarray(mask_obs, dtype=bool) | np.logical_not(np.isfinite(flux_obs))

    rv_grid = np.asarray(rv_grid)
    z_grid = rv_grid / constants.c.value * 1000
    nz = len(z_grid)

    # p = PchipInterpolator(wave_mod, flux_mod, extrapolate=False)
    # p = interp1d(wave_mod, flux_mod, kind="linear", bounds_error=False, fill_value=np.nan)
    # p = Interp1q(wave_mod, flux_mod)

    wave_mod_interp = wave_obs.reshape(1, -1) / (1 + z_grid.reshape(-1, 1))
    flux_mod_interp = np.interp(wave_mod_interp, wave_mod, flux_mod)
    mask_bad = np.logical_not(np.isfinite(flux_mod_interp)) | mask_obs

    # use masked array
    xmod = np.ma.MaskedArray(flux_mod_interp, mask_bad)
    xobs = np.ma.MaskedArray(np.repeat(flux_obs.reshape(1, -1), nz, axis=0), mask_bad)
    xmod -= np.ma.mean(xmod)
    xobs -= np.ma.mean(xobs)

    ccf_grid = np.ma.sum(xmod * xobs, axis=1) / np.ma.sqrt(
        np.ma.sum(xmod * xmod, axis=1) * np.ma.sum(xobs * xobs, axis=1))
    # chi2_grid = 0.5*np.ma.sum((xmod-xobs)**2, axis=1)
    return rv_grid, ccf_grid.data  # , chi2_grid.data


def test_xcorr_rvgrid():
    """ load data """
    wave, flux, flux_err = np.loadtxt('/hydrogen/projects/song/delCep_order20.dat').T
    flux_sine = 1 - flux
    flux_sine = flux_sine * sinebell_like(flux, 1.0)

    flux_obs = flux_sine + np.random.randn(*flux_sine.shape) * 0.5
    wave_mod = wave
    wave_obs = wave
    flux_mod = flux_sine
    rv_grid = np.linspace(-500, 500, 1000)
    # z_grid = rv_grid / constants.c.value * 1000

    ccfv = xcorr_rvgrid(wave_obs, flux_obs,
                        wave_mod, flux_mod, mask_obs=None,
                        rv_grid=rv_grid,
                        sinebell_idx=1)
    plt.figure()
    plt.subplot(211)
    plt.plot(ccfv[0], ccfv[1], 's-')
    # plt.plot(ccfv[0], np.exp(-ccfv[2]+np.max(ccfv[2])), 's-')
    # plt.plot(ccfv[0], (-ccfv[2]+np.mean(ccfv[2]))/np.std(ccfv[2]), 's-')
    plt.hlines(ccfv[1].std() * np.array([0, 3, 5]), -500, 500)
    plt.subplot(212)
    plt.plot(wave, flux_obs)
    plt.plot(wave, flux_sine)

    return


def calculate_local_variance(flux, npix_lv: int = 5) -> np.ndarray:
    """ calculate local variance """
    weight = np.zeros_like(flux, dtype=np.float)
    npix = len(flux)
    for ipix in range(npix_lv, npix - npix_lv):
        weight[ipix] = np.var(flux[ipix - npix_lv:ipix + 1 + npix_lv])
    return weight


def calculate_local_variance_multi(flux, npix_lv: int = 5, n_jobs: int = -1, verbose: int = 10) -> np.ndarray:
    """ calculate local variance """
    nspec, npix = flux.shape
    weight = joblib.Parallel(n_jobs=n_jobs, verbose=verbose)(
        joblib.delayed(calculate_local_variance)(flux[ispec]) for ispec in range(nspec))
    return np.array(weight)


class RVM:
    def __init__(self, pmod, wave_mod, flux_mod, npix_lv=0):
        """
        Parameters:
        -----------
        pmod: (n_model, *)
            parameters of model spectra
        wave_mod: (n_pixel,)
            wavelength of model spectra
        flux_mod: (n_model, n_pixel)
            normalized flux of model spectra
        npix_lv: int
            the length of chunks to evaluate local variance
        """
        print("@RVM: initializing Radial Velocity Machine (RVM)...")
        # set wavelength
        self.wave_mod = wave_mod
        # set parameters
        if pmod.ndim == 2:
            self.pmod = pmod
        else:
            self.pmod = pmod.reshape(1, -1)
        # set flux
        if flux_mod.ndim == 2:
            self.flux_mod = flux_mod
        else:
            self.flux_mod = flux_mod.reshape(1, -1)
        # record shapes
        self.nparam = self.pmod.shape[1]
        self.nmod, self.npix = self.flux_mod.shape
        self.npix_lv = np.int(np.abs(npix_lv))
        # initialize weights
        # assert w_mod is "lv"
        # currently there is only one option
        if npix_lv > 1:
            print("@RVM: calculating local variance ...")
            self.weight_mod = calculate_local_variance_multi(self.flux_mod, npix_lv=npix_lv, n_jobs=-1)

    def measure(self, wave_obs, flux_obs, w_mod=None, w_obs=None, sinebell_idx=0.,
                rv_grid=np.linspace(-600, 600, 100), flux_bounds=(0, 3.)):
        """ measure RV """
        # clip extreme values
        ind3 = (flux_obs > flux_bounds[0]) & (flux_obs < flux_bounds[1])
        flux_obs = np.interp(wave_obs, wave_obs[ind3], flux_obs[ind3])
        # w_obs
        if w_obs is None:
            w_obs = sinebell_like(flux_obs, index=sinebell_idx)
        else:
            w_obs *= sinebell_like(flux_obs, index=sinebell_idx)
        # w_mod
        if w_mod is None:
            w_mod = np.ones_like(self.flux_mod, dtype=float)
        elif w_mod is "lv":
            w_mod = self.weight_mod
        # CCF grid
        ccf_grid = np.zeros((self.flux_mod.shape[0], rv_grid.shape[0]))
        for imod in range(self.nmod):
            ccf_grid[imod] = wxcorr_rvgrid(wave_obs, flux_obs, self.wave_mod, self.flux_mod[imod],
                                           w_mod=w_mod[imod], w_obs=w_obs, rv_grid=rv_grid)[1]
        # CCF max
        ccf_max = np.max(ccf_grid)
        ind_best = np.where(ccf_max == ccf_grid)
        ipmod_best = ind_best[0][0]
        irv_best = ind_best[1][0]
        rv_best = rv_grid[irv_best]
        # CCF opt
        opt = minimize(wxcorr_spec_cost, x0=rv_best,
                       args=(wave_obs, flux_obs, self.wave_mod, self.flux_mod[ipmod_best],
                             w_mod[imod], w_obs),
                       method="BFGS")  # Powell
        # opt = minimize(ccf_cost_interp, x0=rv_best, args=(wave_obs, flux_obs, wave_mod, flux_mod[imod_best]), method="Powell")
        # x = np.interp(wave, wave_obs/(1+opt.x/SOL_kms), flux_obs).reshape(1, -1)
        return dict(rv_opt=np.float(opt.x),
                    rv_err=np.float(opt.hess_inv),
                    rv_best=rv_best,
                    ccfmax=-opt["fun"],
                    success=opt.success,
                    imod=ipmod_best,
                    pmod=self.pmod[ipmod_best],                status=opt["status"])

    def measure2(self, wave_obs, flux_obs, wave_mod, flux_mod, w_obs=None,
                 rv1_init=0, eta_init=0.3, eta_lim=(0.1, 1.0), drvmax=500, drvstep=5, method="Powell"):
        opt = wxcorr_rvgrid_binary(wave_obs, flux_obs, wave_mod, flux_mod,
                                   rv1_init=rv1_init, eta_init=eta_init, eta_lim=eta_lim,
                                   drvmax=drvmax, drvstep=drvstep, w_obs=w_obs,
                                   method=method)
        return opt

    def measure_binary(self, wave_obs, flux_obs, w_obs=None,
                       rv_grid=np.linspace(-600, 600, 100), flux_bounds=(0, 3.),
                       eta_init=0.3, eta_lim=(0.1, 1.0), drvmax=500, drvstep=5, method="Powell"):

        # clip extreme values
        ind3 = (flux_obs > flux_bounds[0]) & (flux_obs < flux_bounds[1])
        flux_obs = np.interp(wave_obs, wave_obs[ind3], flux_obs[ind3])
        # RV1
        rvr1 = self.measure(wave_obs, flux_obs, w_obs=w_obs, rv_grid=rv_grid)
        # best template
        wave_mod = self.wave_mod
        flux_mod = self.flux_mod[rvr1["ipmod_best"]]
        # RV2
        rvr2 = self.measure2(wave_obs, flux_obs, wave_mod, flux_mod, w_obs=w_obs,
                             rv1_init=rvr1["rv_opt"], eta_init=eta_init, eta_lim=eta_lim,
                             drvmax=drvmax, drvstep=drvstep, method=method)

        rvr = dict(rv1=rvr1["rv_opt"],
                   ccfmax1=rvr1["ccfmax"],
                   rv1_best=rvr1["rv_best"],
                   imod=rvr1["imod"],
                   pmod=rvr1["pmod"],
                   success1=rvr1["success"],
                   ccfmax2=rvr2["ccfmax2"],
                   success2=rvr2["success"],
                   rv1_drv_eta0=rvr2["x0"],
                   rv1_drv_eta=rvr2["x"],
                   status1=rvr1["status"],
                   status2=rvr2["status"])
        if method is "BFGS":
            rvr["hess_inv"] = rvr2["hess_inv"]
        return rvr

    def ccf_1mod(self, wave_mod, flux_mod, wave_obs, flux_obs, w_mod=None, w_obs=None, sinebell_idx=0.,
                 rv_grid=np.linspace(-600, 600, 100), flux_bounds=(0, 3.)):
        """ measure RV """
        # clip extreme values
        ind3 = (flux_obs > flux_bounds[0]) & (flux_obs < flux_bounds[1])
        flux_obs = np.interp(wave_obs, wave_obs[ind3], flux_obs[ind3])
        # w_obs
        if w_obs is None:
            w_obs = sinebell_like(flux_obs, index=sinebell_idx)
        else:
            w_obs *= sinebell_like(flux_obs, index=sinebell_idx)
        # w_mod
        if w_mod is None:
            w_mod = np.ones_like(flux_mod, dtype=float)
        # elif w_mod is "lv":
        #     w_mod = self.weight_mod
        # CCF grid
        ccf_grid = wxcorr_rvgrid(wave_obs, flux_obs, wave_mod, flux_mod,
                                 w_mod=w_mod, w_obs=w_obs, rv_grid=rv_grid)[1]
        return rv_grid, ccf_grid

    def chi2_1mod(self, imod, wave_obs, flux_obs, rv_grid=np.linspace(-600, 600, 100), pw=2, flux_bounds=(0, 3.)):
        """ measure RV """
        # clip extreme values
        ind3 = (flux_obs > flux_bounds[0]) & (flux_obs < flux_bounds[1])
        flux_obs = np.interp(wave_obs, wave_obs[ind3], flux_obs[ind3])
        # respw grid
        respw_grid = respw_rvgrid(wave_obs, flux_obs, self.wave_mod, self.flux_mod[imod], rv_grid=rv_grid, pw=pw)
        return rv_grid, respw_grid

    def measure_pw(self, wave_obs, flux_obs, rv_grid=np.linspace(-600, 600, 100), method="BFGS", pw=1):
        # clip extreme values
        ind3 = (flux_obs < 3) & (flux_obs > 0.)
        flux_obs = np.interp(wave_obs, wave_obs[ind3], flux_obs[ind3])
        # CCF grid
        ccf = np.zeros((self.flux_mod.shape[0], rv_grid.shape[0]))
        for j in range(self.flux_mod.shape[0]):
            ccf[j] = wxcorr_rvgrid(wave_obs, flux_obs, self.wave_mod, self.flux_mod[j], rv_grid=rv_grid)[1]
        # CCF max
        ccfmax = np.max(ccf)
        ind_best = np.where(ccfmax == ccf)
        ipmod_best = ind_best[0][0]
        irv_best = ind_best[1][0]
        rv_best = rv_grid[irv_best]
        # CCF opt
        opt = minimize(respw_cost, x0=rv_best,
                       args=(wave_obs, flux_obs, self.wave_mod, self.flux_mod[ipmod_best], pw), method=method)
        # opt = minimize(ccf_cost_interp, x0=rv_best, args=(wave_obs, flux_obs, wave_mod, flux_mod[imod_best]), method="Powell")
        # x = np.interp(wave, wave_obs/(1+opt.x/SOL_kms), flux_obs).reshape(1, -1)
        return dict(rv_opt=np.float(opt.x),
                    rv_err=np.float(opt.hess_inv) if method is "BFGS" else np.nan,
                    rv_best=rv_best,
                    ccfmax=ccfmax,
                    success=opt.success,
                    ipmod_best=ipmod_best,
                    pmod_best=self.pmod[ipmod_best],
                    opt=opt)


# def test_rvm_v2():
#     import joblib
#     from laspec.ccf import RVM
#     rvm = RVM(joblib.load("/Users/cham/projects/sb2/data/v8_rvm_pmod.dump"),
#               joblib.load("/Users/cham/projects/sb2/data/v8_rvm_wave_mod.dump"),
#               joblib.load("/Users/cham/projects/sb2/data/v8_rvm_flux_mod.dump"), npix_lv=5)
#     return

# nrvmod = 32
# tgma_rvmod = tgma1[np.random.choice(np.arange(nstar, dtype=int), nrvmod)]
# flux_rvmod = np.array([predict_single_star(r,r.wave,_,0,True) for _ in tgma_rvmod])
# rvm = RVM(tgma_rvmod, r.wave, flux_rvmod)


def test_lmfit():
    """ load data """
    wave, flux, flux_err = np.loadtxt('/hydrogen/projects/song/delCep_order20.dat').T
    flux_sine = 1 - flux
    flux_sine = flux_sine * sinebell_like(flux, 1.0)

    flux_obs = flux_sine + np.random.randn(*flux_sine.shape) * 0.1
    wave_mod = wave
    wave_obs = wave
    flux_mod = flux_sine
    rv_grid = np.linspace(-500, 500, 1000)
    # z_grid = rv_grid / constants.c.value * 1000

    ccfv = xcorr_rvgrid(wave_obs, flux_obs,
                        wave_mod, flux_mod, mask_obs=None,
                        rv_grid=rv_grid,
                        sinebell_idx=1)

    # Gaussian fit using LMFIT
    from lmfit.models import GaussianModel

    mod = GaussianModel()
    x, y = ccfv[0], ccfv[1]
    # pars = mod.guess(y, x=x)
    out = mod.fit(y, None, x=x, method="least_squares")
    # out = mod.fit(y, pars, x=x, method="leastsq")

    plt.figure()
    plt.plot(x, y)
    plt.plot(x, out.best_fit)
    print(out.fit_report())


def test_new_rvm():
    import joblib
    from laspec.ccf import RVM
    rvm = RVM(joblib.load("/Users/cham/PycharmProjects/laspec/laspec/data/rvm/v8_rvm_pmod.dump"),
              joblib.load("/Users/cham/PycharmProjects/laspec/laspec/data/rvm/v8_rvm_wave_mod.dump"),
              joblib.load("/Users/cham/PycharmProjects/laspec/laspec/data/rvm/v8_rvm_flux_mod.dump"))

    waveBR, spec_list = joblib.load("/Users/cham/projects/sb2/test_ccf/wave_flux_30.dump")
    wave_obs = waveBR[waveBR < 5500]
    npix = len(wave_obs)
    # %%%% read spectra
    import glob
    fps = glob.glob("./*.fits.gz")

    from laspec.mrs import MrsSource, debad
    ms = MrsSource.read(fps)

    # %%
    fig, axs = plt.subplots(1, 2)
    for i, me in enumerate(ms[:1]):
        # wave_obs = me.wave_B
        # flux_obs = me.flux_norm_B
        wave_obs, flux_obs = me.wave_B[50:-50], debad(me.wave_B, me.flux_norm_B, nsigma=(4, 8), maxiter=5)[50:-50]
        axs[0].plot(wave_obs, flux_obs + i, "k")

        # measure RV
        rvr = rvm.measure(wave_obs, flux_obs)
        print(rvr)
        ipmod_best = rvr["ipmod_best"]
        rv_grid, ccf_grid = rvm.ccf_1mod(rvm.wave_mod, rvm.flux_mod[ipmod_best], wave_obs, flux_obs, w_mod=None,
                                         rv_grid=np.arange(-2000, 2000, 5))
        axs[1].plot(rv_grid, ccf_grid + i, "b")

    # %%time
    from collections import OrderedDict
    rvr = []

    for i, me in enumerate(ms[:]):
        print(i)

        # wave_obs = me.wave_B
        # flux_obs = me.flux_norm_B

        # remove cosmic rays
        wave_obs, flux_obs = me.wave_B[50:-50], debad(me.wave_B, me.flux_norm_B, nsigma=(4, 8), maxiter=5)[50:-50]
        # measure binary
        this_rvr = rvm.measure_binary(wave_obs, flux_obs, w_obs=None,
                                      rv_grid=np.arange(-600, 600, 10), flux_bounds=(0, 3.),
                                      eta_init=0.3, drvmax=500, drvstep=5, method="Powell")
        this_rvr["lmjm"] = me.epoch
        this_rvr["snr"] = me.snr[0]
        # append results
        rvr.append(this_rvr)

    from astropy.table import Table
    trvr = Table(rvr)
    trvr.write("./trvr.fits", overwrite=True)
    trvr.show_in_browser()
    # %%
    figure()
    plot(trvr["snr"], trvr["ccfmax1"], 'bo')
    plot(trvr["snr"], trvr["ccfmax2"], 'ro')
    ylim(0, 1)
    # %%
    figure()
    plot(trvr["lmjm"], trvr["rv1_drv_eta"][:, 0], 'ro', label="star 1")
    plot(trvr["lmjm"], trvr["rv1_drv_eta"][:, 0] + trvr["rv1_drv_eta"][:, 1], 'bo', label="star 2")
    legend(loc="right")
    xlabel("lmjm")
    ylabel("RV[km/s]")


if __name__ == "__main__":
    test_xcorr_rvgrid()
