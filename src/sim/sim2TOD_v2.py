import numpy as np
import h5py
import matplotlib.pyplot as plt
import WCS
import time
import shutil
from tqdm import trange
import sys 
import argparse
import re
from tsysmeasure import TsysMeasure

class Sim2TOD:
    def __init__(self):
        """
        Initializing class and setting class attributes.
        """
        self.nside = 120   # Number of pixels in each direction.
        self.dpix = 2.0 / 60.0  # Pixel resolution in degrees (here, 2 arcminutes)
        self.Tsys = TsysMeasure()
        self.input()

    def run(self):
        """
        Function to run through the process of opening TOD and add simulated
        data from a datacube.
        """
        t = time.time()
        print("Processing Parameterfile: "); t0 = time.time()
        self.read_paramfile()
        
        print("Time: ", time.time()-t0, " sec")
        print("Loading Cube: "); t0 = time.time()
        self.load_cube()
        
        print("Time: ", time.time()-t0, " sec")
        print("Loopig through runlist: "); t0 = time.time()
        for i in trange(len(self.tod_in_list)):
            self.tod_in_filename    = self.tod_in_path + self.tod_in_list[i]
            self.tod_out_filename   = self.tod_out_path + self.tod_in_list[i]
            
            print("Time: ", time.time()-t0, " sec")
            print("Copying Outfile: "); t0 = time.time()
        
            self.make_outfile()
        
            print("Time: ", time.time()-t0, " sec")
            print("Loading TOD: "); t0 = time.time()        
            self.load_tod()
        
            print("Time: ", time.time()-t0, " sec")
            print("Calculating Tsys: "); t0 = time.time()        
            self.calc_tsys()
        
            print("Time: ", time.time()-t0, " sec")
            if self.whitenoise:
                print("Writing noise-data to TOD: "); t0 = time.time()
                self.write_white_noise()
            else:
                print("Writing sim-data to TOD: "); t0 = time.time()
                self.write_sim()
        
        print("Run time: ", time.time() - t, " sec")
        

    def input(self):
        """
        Function parsing the command line input.
        """
        parser = argparse.ArgumentParser()
        parser.add_argument("-p", "--param", type = str,
                            help = """Full path and name to parameter file 
                                    containing all needed info to add simulations to
                                    l1 files.""")
        
        parser.add_argument("-n", "--norm", type = float, default = 1.0,
                            help = """Normalize simulation cube by input value.""")
        
        parser.add_argument("-w", "--whitenoise", action = "store_true",
                            help = """Add white noise to TOD.""")
        
        args = parser.parse_args()
        
        if args.param == None:
            message = """No input parameterfile given, please provide an input parameterfile"""
            raise NameError(message)
        else:
            self.param_file     = args.param
            self.norm           = args.norm
            self.whitenoise     = args.whitenoise
        
    def read_paramfile(self):
        """
        Function reading the parameter file provided by the command line
        argument, and defining class parameters.
        """
        param_file  = open(self.param_file, "r")
        params      = param_file.read()

        runlist_path = re.search(r"\nRUNLIST\s*=\s*'(\/.*?)'", params)  # Defining regex pattern to search for runlist path in parameter file.
        self.runlist_path = str(runlist_path.group(1))                  # Extracting path
        
        tod_in_path = re.search(r"\nTOD_IN_DIR\s*=\s*'(\/.*?)'", params)    # Defining regex pattern to search for level1 file path.
        self.tod_in_path = str(tod_in_path.group(1))                        # Extracting path
        
        tod_out_path = re.search(r"\nTOD_OUT_DIR\s*=\s*'(\/.*?)'", params)   # Defining regex pattern to search for level1 file with added simulation path.
        self.tod_out_path = str(tod_out_path.group(1))                          # Extracting path
        
        cube_path = re.search(r"\nDATACUBE\s*=\s*'(\/.*?\.\w+)'", params)   # Defining regex pattern to search for simulation cube file path.
        self.cube_filename = str(cube_path.group(1))                        # Extracting path

        runlist_file = open(self.runlist_path, "r")         # Opening 
        runlist = runlist_file.read()
        tod_in_list = re.findall(r"\/.*?\.\w+", runlist)
        self.tod_in_list = tod_in_list

        patch_name = re.search(r"\s([a-zA-Z0-9]+)\s", runlist)
        self.patch_name = str(patch_name.group(1))

        patch_def_path = re.search(r"\nPATCH_DEFINITION_FILE\s*=\s*'(\/.*?)'", params)
        self.patch_def_path = str(patch_def_path.group(1))

        patch_def_file = open(self.patch_def_path, "r")
        patch_def = patch_def_file.read()
        fieldcent   = re.search(rf"{self.patch_name}\s*([0-9.]+)\s*([0-9.]+)", patch_def) 
        self.fieldcent = [eval(fieldcent.group(1)), eval(fieldcent.group(2))]
        
        print("Patch def:", self.patch_def_path)
        print("Patch", self.patch_name)
        print("Field center", self.fieldcent)
        print("Runlist:", self.runlist_path)
        print("TOD in:", self.tod_in_path)
        print("TOD out:", self.tod_out_path)
        print("Cube:", self.cube_filename)
        print("# obsID", len(self.tod_in_list))
        print("obsID #1: ", self.tod_in_list[0])
        

    def load_cube(self):
        """
        Read the simulated datacube into memory.
        """
        cube = np.load(self.cube_filename)
        cubeshape = cube.shape

        cube /= self.norm    # Normalization of cube by input value

        cube = cube.reshape(cubeshape[0] * cubeshape[1], 4, 1024)  # Flatten the x/y dims, and split the frequency (depth) dim in 4 sidebands.
        cube = cube.transpose(1, 2, 0)  # Reorder dims such that the x/y dim is last, and the frequencies first (easier to deal with later).
        cube[0, :, :] = cube[0, ::-1, :]    # Flipping sideband 0 and 2 to fit the TOD
        cube[2, :, :] = cube[2, ::-1, :]
        self.cube = cube 

    def make_outfile(self):
        """
        Create a copy of the input level1 file, such that we can simply replace the TOD with simulated data later.
        """
        shutil.copyfile(self.tod_in_filename, self.tod_out_filename)

    def load_tod(self):
        """
        Load the TOD and other relevant data from the level1 file into memory.
        """
        infile        = h5py.File(self.tod_in_filename, "r")

        vane_angles    = np.array(infile["/hk/antenna0/vane/angle"])[()]/100.0  # Degrees
        vane_time      = np.array(infile["/hk/antenna0/vane/utc"])[()]
        array_features = np.array(infile["/hk/array/frame/features"])[()]
        tod_times      = np.array(infile["/spectrometer/MJD"])[()]
        self.freq      = np.array(infile["spectrometer/frequency"])[()]
        
        self.feeds    = np.array(infile["/spectrometer/feeds"])[()]
        self.nfeeds   = len(self.feeds)
        self.tod            = np.array(infile["/spectrometer/tod"])[()].astype(dtype=np.float32, copy=False)
        
        self.ra       = np.array(infile["/spectrometer/pixel_pointing/pixel_ra"])[()]
        self.dec      = np.array(infile["/spectrometer/pixel_pointing/pixel_dec"])[()]
        self.tod_sim  = self.tod.copy()  # The simulated data is, initially, simply a copy of the original TOD.
        self.dt = np.abs(tod_times[1] - tod_times[0])
        self.dnu = np.abs(self.freq[0, 1] - self.freq[0, 0])
        
        if tod_times[0] > 58712.03706:
            T_hot      = np.array(infile["/hk/antenna0/vane/Tvane"])[()]
        else:
            T_hot      = np.array(infile["/hk/antenna0/env/ambientLoadTemp"])[()]

        self.Tsys.load_data_from_arrays(vane_angles, vane_time, array_features, T_hot, self.tod, tod_times)
        infile.close()
        

    def calc_tsys(self):
        self.Tsys.solve()

        self.tsys = self.Tsys.Tsys_of_t(self.Tsys.tod_times, self.Tsys.tod)
        """
        first_cal_idx = self.Tsys.calib_indices_tod[0, :]
        second_cal_idx = self.Tsys.calib_indices_tod[1, :]
        tod_start = int(first_cal_idx[1])
        tod_end = int(second_cal_idx[0])
        self.tsys = 40
        """
    
    def write_sim(self):
        nside, dpix, fieldcent, ra, dec, tod, cube, tsys, nfeeds = self.nside, self.dpix, self.fieldcent, self.ra, self.dec, self.tod, self.cube, self.tsys, self.nfeeds
        pixvec = np.zeros_like(dec, dtype = int)
        first_cal_idx = self.Tsys.calib_indices_tod[0, :]
        second_cal_idx = self.Tsys.calib_indices_tod[1, :]
        tod_start = int(first_cal_idx[1])
        tod_end = int(second_cal_idx[0])

        for i in trange(nfeeds):  # Don't totally understand what's going on here, it's from Håvards script.
            # Create a vector of the pixel values which responds to the degrees we send in.
            pixvec[i, :] = WCS.ang2pix([nside, nside], [-dpix, dpix], fieldcent, dec[i, :], ra[i, :])     
            # Update tod_sim values.
            self.tod_sim[i, :, :, tod_start + 1:tod_end - 1] *= 1 + cube[ ..., pixvec[i, tod_start + 1:tod_end - 1]] / tsys[i, :, :, tod_start + 1:tod_end - 1]
            #self.tod_sim[i, :, :,tod_start:tod_end] *= 1 + cube[ ..., pixvec[i, tod_start:tod_end]] / tsys
        self.tod_sim = np.where(self.tsys > 0, self.tod_sim, 0)
        self.tod_sim = np.where(self.tsys < 200, self.tod_sim, 0)

        with h5py.File(self.tod_out_filename, "r+") as outfile:  # Write new sim-data to file.
            data = outfile["/spectrometer/tod"] 
            data[...] = self.tod_sim
        outfile.close()

    def write_white_noise(self):
        nside, dpix, fieldcent, ra, dec, tod, cube, tsys, nfeeds = self.nside, self.dpix, self.fieldcent, self.ra, self.dec, self.tod, self.cube, self.tsys, self.nfeeds
        shape = tsys.shape

        noise   = np.random.normal(0, np.abs(tsys).reshape(np.prod(shape)) / np.sqrt(self.dt * self.dnu)).reshape(shape)
        
        pixvec = np.zeros_like(dec, dtype = int)
        first_cal_idx = self.Tsys.calib_indices_tod[0, :]
        second_cal_idx = self.Tsys.calib_indices_tod[1, :]
        tod_start = int(first_cal_idx[1])
        tod_end = int(second_cal_idx[0])

        for i in trange(nfeeds):  # Don't totally understand what's going on here, it's from Håvards script.
            # Create a vector of the pixel values which responds to the degrees we send in.
            pixvec[i, :] = WCS.ang2pix([nside, nside], [-dpix, dpix], fieldcent, dec[i, :], ra[i, :])     
            # Update tod_sim values.
            self.tod_sim[i, :, :, tod_start + 1:tod_end - 1] *= 1 + noise[i, :, :, tod_start + 1:tod_end - 1] / tsys[i, :, :, tod_start + 1:tod_end - 1]
        
        self.tod_sim = np.where(self.tsys > 0, self.tod_sim, 0)
        self.tod_sim = np.where(self.tsys < 200, self.tod_sim, 0)

        with h5py.File(self.tod_out_filename, "r+") as outfile:  # Write new sim-data to file.
            data = outfile["/spectrometer/tod"] 
            data[...] = self.tod_sim
        outfile.close()


if __name__ == "__main__":
    sim2tod = Sim2TOD()
    sim2tod.run()
    