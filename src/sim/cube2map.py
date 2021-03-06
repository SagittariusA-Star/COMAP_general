import numpy as np
import h5py
import time
import shutil
import matplotlib.pyplot as plt
import WCS

class cube2map:
    def __init__(self, cube_filename, map_in_filename, map_out_filename):
        self.cube_filename = cube_filename          # Filepath of simulated cube.
        self.map_in_filename = map_in_filename      # Filepath of already existing level1 file.
        self.map_out_filename = map_out_filename    # Filepath of simulated output level1 file.
        
    def run(self):
        print("Loading Cube"); 
        t0 = time.time()
        self.load_cube()
        print("Time: ", time.time()-t0, " sec")
        print("Copying outfile"); 
        t0 = time.time()
        self.make_outfile()
        print("Time: ", time.time()-t0, " sec"); 
        t0 = time.time()
        print("Saving cube to map file")
        self.save_outfile()
        print("Time: ", time.time()-t0, " sec"); 
        
    def load_cube(self):
        """
        Read the simulated datacube into memory.
        """
        cube = np.load(cube_filename)
        cubeshape = cube.shape
        cube = cube.reshape(cubeshape[0], cubeshape[1], 4, 1024)  # Flatten the x/y dims, and split the frequency (depth) dim in 4 sidebands.
        cube = cube.reshape(cubeshape[0], cubeshape[1], 4, 64, 16)
        cube = np.mean(cube, axis = -1)     # Averaging over 16 frequency channels
        cube = cube.transpose(2, 3, 0, 1)        # Reorder dims such that the x/y dim is last, and the frequencies first (easier to deal with later).
        cube /= np.max(cube)     # Normalizing cube so that the max value is 1 K
        #cube -= np.mean(cube, axis = (0, 1))    # Normalizing cube so that the max value is 1 K
        #cube -= np.mean(cube)    # Normalizing cube so that the max value is 1 K
        cube = cube.reshape(4, 64, 120 * 120)
        self.cube = cube

    def make_outfile(self):
        """
        Create a copy of the input level1 file, such that we can simply replace the map with simulated data later.
        """
        shutil.copyfile(self.map_in_filename, self.map_out_filename)
    
    def save_outfile(self):
        with h5py.File(self.map_in_filename, "r") as outfile:
            map_coadd   = outfile["map_coadd"]
            print("Max in: ", np.nanmax(np.array(map_coadd)))
            print("Min in: ", np.nanmin(np.array(map_coadd)))
        
        with h5py.File(self.map_out_filename, "r+") as outfile:
            map     = outfile["map"]
            rms     = outfile["rms"]
            nhit    = outfile["nhit"]
            map[...]    = np.zeros_like(map)
            rms[...]    = np.zeros_like(rms)
            nhit[...]   = np.zeros_like(nhit)
            
            pixvec = np.load("Observed_pixels.npy")
            pixvec = np.unique(pixvec)
            
            fieldcent = np.array(outfile["patch_center"])
            ra      = np.array(outfile["x"])
            dec     = np.array(outfile["y"])
            nside   = len(ra)
            #dpix    = ra[1] - ra[0]
            dpix    = 2.0 / 60.0
            print(dpix, ra[1] - ra[0], dec[1] - dec[0])
            
            RA, DEC = np.meshgrid(ra, dec, indexing = "ij")
            RA, DEC = RA.flatten(), DEC.flatten()

            pix = WCS.ang2pix([nside, nside], [-dpix, dpix], fieldcent, DEC, RA)
            print(np.max(pix), np.min(pix), 120 * 120, np.max(pixvec))
            #print(fieldcent, (ra[0] + ra[-1]) / 2, (dec[0] + dec[-1]) / 2)
            #print(nside, dpix)
            
            #nhit_masked = - np.ones_like(self.cube)
            nhit_masked = np.zeros_like(self.cube)
            #nhit_masked[:, :, pixvec] = 1  
            nhit_masked[:, :, pix] = 1  
            nhit_masked = nhit_masked.reshape(4, 64, 120, 120)
            nhit_masked = nhit_masked.transpose(0, 1, 3, 2)
            cube = self.cube
            cube = cube.reshape(4, 64, 120, 120)
            cube = cube.transpose(0, 1, 3, 2)

            try:
                map_coadd   = outfile["map_coadd"]
                rms_coadd   = outfile["rms_coadd"]
                nhit_coadd  = outfile["nhit_coadd"]
                map_coadd[...]  = cube
                rms_coadd[...]  = np.ones(rms_coadd.shape)
                nhit_coadd[...] = nhit_masked
                #nhit_coadd[...] = np.ones(nhit_coadd.shape)
                print("Max out: ", np.nanmax(np.array(map_coadd)))
                print("Min out: ", np.nanmin(np.array(map_coadd)))

            except KeyError:
                map_beam   = outfile["map_beam"]
                rms_beam   = outfile["rms_beam"]
                nhit_beam  = outfile["nhit_beam"]
                map_beam[...]  = self.cube
                rms_beam[...]  = np.ones(rms_beam.shape)
                nhit_beam[...] = np.ones(nhit_beam.shape)
                    


if __name__ == "__main__":
    cube_path = "/mn/stornext/d16/cmbco/comap/protodir/"
    cube_filename = cube_path + "cube_real.npy"
    
    map_in_path = "/mn/stornext/d16/cmbco/comap/nils/COMAP_general/data/maps/sim/"
    map_in_filename = map_in_path + "co6_map.h5"

    map_out_path = "/mn/stornext/d16/cmbco/comap/nils/COMAP_general/data/maps/sim/"
    map_out_filename =  map_out_path + "co6_cube_proj_map.h5"

    cube2map = cube2map(cube_filename, map_in_filename, map_out_filename)
    cube2map.run()