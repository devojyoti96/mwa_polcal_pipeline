from casatools import table, msmetadata
import numpy as np,os, psutil, time, glob


def freq_to_MWA_coarse(freq):
    """
    Frequency to MWA coarse channel conversion

    Parameters
    ----------
    freq : float
            Frequency in MHz
    Returns
    -------
    int
            MWA coarse channel number
    """
    freq = float(freq)
    coarse_chans = [[(i * 1.28) - 0.64, (i * 1.28) + 0.64] for i in range(300)]
    for i in range(len(coarse_chans)):
        ch0 = round(coarse_chans[i][0], 2)
        ch1 = round(coarse_chans[i][1], 2)
        if freq >= ch0 and freq < ch1:
            return i


def get_chans_flags(msname):
    """
    Get channels flagged or not
    Parameters
    ----------
    msname : str
        Name of the measurement set
    Returns
    -------
    numpy.array
        A boolean array indicating whether the channel is completely flagged or not
    """
    tb = table()
    tb.open(msname)
    flag = tb.getcol("FLAG")
    tb.close()
    chan_flags = np.all(np.all(flag, axis=-1), axis=0)
    return chan_flags


def MWA_field_of_view(msname, FWHM=True):
    """
    Calculate optimum field of view in arcsec
    Parameters
    ----------
    msname : str
        Name of the measurement set
    FWHM : bool
            Upto FWHM, otherwise upto first null
    Returns
    -------
    float
            Field of view in arcsec
    """
    msmd = msmetadata()
    msmd.open(msname)
    freq = msmd.meanfreq(0)
    msmd.close()
    if FWHM == True:
        FOV = (
            np.sqrt(610) * 150 * 10**6 / freq
        )  # 600 deg^2 is the image FoV at 150MHz for MWA. So extrapolating this to central frequency
    else:
        FOV = (
            60 * 110 * 10**6 / freq
        )  # 3600 deg^2 is the image FoV at 110MHz for MWA upto first null. So extrapolating this to central frequency
    return FOV * 3600  ### In arcsecs


def calc_psf(msname):
    """
    Function to calculate PSF size in arcsec
    Parameters
    ----------
    msname : str
        Name of the measurement set
    Returns
    -------
    float
            PSF size in arcsec
    """
    maxuv_m, maxuv_l = calc_maxuv(msname)
    psf = np.rad2deg(1.2 / maxuv_l) * 3600.0  # In arcsec
    return psf


def calc_cellsize(msname, num_pixel_in_psf):
    """
    Calculate pixel size in arcsec
    Parameters
    ----------
    msname : str
        Name of the measurement set
    num_pixel_in_psf : int
            Number of pixels in one PSF
    Returns
    -------
    int
            Pixel size in arcsec
    """
    psf = calc_psf(msname)
    pixel = int(psf / num_pixel_in_psf)
    return pixel


def calc_imsize(msname, num_pixel_in_psf):
    """
    Calculate image pixel size
    Parameters
    ----------
    msname : str
        Name of the measurement set
    num_pixel_in_psf : int
            Number of pixels in one PSF
    Returns
    -------
    int
            Number of pixels
    """
    cellsize = calc_cellsize(msname, num_pixel_in_psf)
    fov = MWA_field_of_view(msname, FWHM=True)
    imsize = int(fov / cellsize)
    pow2 = round(np.log2(imsize / 10.0), 0)
    imsize = int((2**pow2) * 10)
    if imsize > 8192:
        imsize = 8192
    return imsize


def calc_multiscale_scales(msname, num_pixel_in_psf, max_scale=16):
    """
    Calculate multiscale scales
    Parameters
    ----------
    msname : str
        Name of the measurement set
    num_pixel_in_psf : int
            Number of pixels in one PSF
    max_scale : float
        Maximum scale in arcmin
    Returns
    -------
    list
            Multiscale scales in pixel units
    """
    psf = calc_psf(msname)
    multiscale_scales = [0, num_pixel_in_psf]
    max_scale_pixel = int(max_scale * 60 / psf)
    other_scales = np.linspace(3 * num_pixel_in_psf, max_scale_pixel, 3).astype("int")
    for scale in other_scales:
        multiscale_scales.append(scale)
    return multiscale_scales


def calc_maxuv(msname):
    """
    Calculate maximum UV
    Parameters
    ----------
    msname : str
        Name of the measurement set
    Returns
    -------
    float
        Maximum UV in meter
    float
        Maximum UV in wavelength
    """
    msmd = msmetadata()
    msmd.open(msname)
    freq = msmd.meanfreq(0)
    wavelength = 299792458.0 / (freq)
    msmd.close()
    tb = table()
    tb.open(msname)
    uvw = tb.getcol("UVW")
    tb.close()
    u, v, w = [uvw[i, :] for i in range(3)]
    maxu = float(np.nanmax(u))
    maxv = float(np.nanmax(v))
    maxuv = np.nanmax([maxu, maxv])
    return maxuv, maxuv / wavelength


def calc_bw_smearing_freqwidth(msname):
    """
    Function to calculate spectral width to procude bandwidth smearing
    Parameters
    ----------
    msname : str
        Name of the measurement set
    Returns
    -------
    float
        Spectral width in MHz
    """
    R = 0.9
    fov = 3600  # 2 times size of the Sun
    psf = calc_psf(msname)
    msmd = msmetadata()
    msmd.open(msname)
    freq = msmd.meanfreq(0)
    msmd.close()
    delta_nu = np.sqrt((1 / R**2) - 1) * (psf / fov) * freq
    delta_nu /= 10**6
    return round(delta_nu, 2)


def get_calibration_uvrange(msname):
    """
    Calibration baseline range suitable for GLEAM model
    Parameters
    ----------
    msname : str
        Name of the measurement set
    Returns
    -------
    str
        UV-range for the calibration
    """
    msmd = msmetadata()
    msmd.open(msname)
    freq = msmd.meanfreq(0)
    msmd.close()
    wavelength = (3 * 10**8) / freq
    minuv_m=112
    maxuv_m=2500
    minuv_l=round(minuv_m/wavelength,1)
    maxuv_l=round(maxuv_m/wavelength,1)
    uvrange=str(minuv_l)+'~'+str(maxuv_l)+'lambda'
    return uvrange
 
def create_batch_script_nonhpc(cmd, basedir, basename):
    """
    Function to make a batch script not non-HPC environment
    Parameters
    ----------
    cmd : str
            Command to run
    basedir : str
            Base directory of the measurement set
    basename : str
            Base name of the batch files
    """
    batch_file = basedir + "/" + basename + ".batch"
    cmd_batch = basedir + "/" + basename + "_cmd.batch"
    if os.path.isdir(basedir + "/logs") == False:
        os.makedirs(basedir + "/logs")
    outputfile = basedir + "/logs/" + basename + ".log"
    pid_file = basedir + "/pids.txt"
    finished_touch_file = basedir + "/.Finished_" + basename
    os.system("rm -rf " + finished_touch_file + "*")
    finished_touch_file_error = finished_touch_file + "_error"
    finished_touch_file_success = finished_touch_file + "_0"
    cmd_file_content = f"""{cmd}\nsleep 2 \nexit_code=$?\nif [ $? -ne 0 ]\nthen touch {finished_touch_file_error}\nelse touch {finished_touch_file_success}\nfi"""
    batch_file_content = f"""export PYTHONUNBUFFERED=1\nnohup sh {cmd_batch}> {outputfile} 2>&1 &\necho $! >> {pid_file}\nsleep 2\n rm -rf {batch_file}\n rm -rf {cmd_batch}"""
    if os.path.exists(cmd_batch):
        os.system("rm -rf " + cmd_batch)
    if os.path.exists(batch_file):
        os.system("rm -rf " + batch_file)
    with open(cmd_batch, "w") as cmd_batch_file:
        cmd_batch_file.write(cmd_file_content)
    with open(batch_file, "w") as b_file:
        b_file.write(batch_file_content)
    os.system("chmod a+rwx " + batch_file)
    os.system("chmod a+rwx " + cmd_batch)
    del cmd
    return basedir + "/" + basename + ".batch"    
 
def get_column_size(msname,colname):
    """
    Get a column size in GB
    Parameters
    ----------
    msname : str
        Name of the ms
    colname : str
        Name of the column
    Returns
    -------
    float
        Size of the column in GB
    """            
    tb = table()
    tb.open(msname)
    if colname not in tb.colnames():
        print("No "+colname+" column found in this Measurement Set.")
        tb.close()
        return 0
    # Get the shape of the DATA column and the number of rows
    data_desc = tb.getcolshapestring(colname)[0]
    data_shape_0 = int(data_desc.split(',')[0].split('[')[-1])  # shape of each entry (channels, polarization)
    data_shape_1 = int(data_desc.split(', ')[-1].split(']')[0])
    num_rows = tb.nrows()
    bytes_per_element = 16
    # Calculate the estimated size
    estimated_size_bytes = num_rows * data_shape_0 * data_shape_1 * bytes_per_element
    estimated_size_gb = estimated_size_bytes / (1024**3)
    tb.close()
    return estimated_size_gb
                 
def check_resource_availability(cpu_threshold=20, memory_threshold=20):
    """
    Check hardware resource availability
    Parameters
    ----------
    cpu_threshold : float
        Percentage of free CPU
    memory_threshold : float
        Percentage of free memory
    Returns
    -------
    bool
        Whether sufficient hardware resource is available or not
    """         
    # Check CPU availability
    current_cpu_usage = psutil.cpu_percent(interval=1)
    cpu_available = current_cpu_usage < (100 - cpu_threshold)
    # Check Memory availability
    memory = psutil.virtual_memory()
    memory_available = memory.available / memory.total * 100
    memory_sufficient = memory_available > memory_threshold
    # Check Swap Memory availability
    # Check Swap availability
    swap = psutil.swap_memory()
    swap_available = swap.free / swap.total * 100 if swap.total > 0 else 100  # 100% if no swap is configured
    swap_sufficient = swap_available > memory_threshold
    return cpu_available and memory_sufficient and swap_sufficient

def wait_for_resources(finished_file_prefix, cpu_threshold=20, memory_threshold=20):
    """
    Wait for free hardware resources
    Parameters
    ----------
    finished_file_prefix : str
        Finished file prefix name 
    cpu_threshold : float
        Percentage of free CPU
    memory_threshold : float
        Percentage of free memory 
    Returns
    -------
    int
        Number of free jobs      
    """
    time.sleep(5)
    count=0
    finished_file_list=glob.glob(finished_file_prefix+'*')
    while True:
        resource_available=check_resource_availability(cpu_threshold=cpu_threshold, memory_threshold=memory_threshold)
        if resource_available:
            new_finished_file_list=glob.glob(finished_file_prefix+'*')
            if len(new_finished_file_list)-len(finished_file_list)>0:
                free_jobs=len(new_finished_file_list)-len(finished_file_list)
                return free_jobs
            else:   
                if count==0:
                    print ('Waiting for free hardware resources ....\n')  
                time.sleep(10) 
        else: 
            if count==0:
                print ('Waiting for free hardware resources ....\n')  
            time.sleep(10)
        count+=1     
        
        
          
    
