#!/usr/bin/env python2
import os
import json
import re
import shutil
import hashlib
import scipy
import h5py
import time
import numpy as np
import tifffile as tf
from skimage import exposure
from skimage import img_as_ubyte
import scipy.io as spio
import numpy as np
from stat import S_IREAD, S_IRGRP, S_IROTH, S_IWRITE, S_IWGRP, S_IWOTH

# -----------------------------------------------------------------------------
# Commonly used, generic methods:
# -----------------------------------------------------------------------------
def atoi(text):
    return int(text) if text.isdigit() else text

def natural_keys(text):
    return [ atoi(c) for c in re.split('(\d+)', text) ]

def default_filename(slicenum, channelnum, filenum, acq=None, run=None):
    fn_base = 'Slice%02d_Channel%02d_File%03d' % (slicenum, channelnum, filenum)
    if run is not None:
        fn_base = '%s_%s' % (run, fn_base)
    if acq is not None:
        fn_base = '%s_%s' % (acq, fn_base)
    return fn_base

def print_elapsed_time(t_start):
    hours, rem = divmod(time.time() - t_start, 3600)
    minutes, seconds = divmod(rem, 60)
    print "Duration: {:0>2}:{:0>2}:{:05.2f}".format(int(hours),int(minutes),seconds)

# -----------------------------------------------------------------------------
# Data-saving and -formatting methods:
# -----------------------------------------------------------------------------
def jsonify_array(curropts):
    jsontypes = (list, tuple, str, int, float, bool, unicode, long)
    for pkey in curropts.keys():
        if isinstance(curropts[pkey], dict):
            for subkey in curropts[pkey].keys():
                if curropts[pkey][subkey] is not None and not isinstance(curropts[pkey][subkey], jsontypes) and len(curropts[pkey][subkey].shape) > 1:
                    curropts[pkey][subkey] = curropts[pkey][subkey].tolist()
    return curropts

def write_dict_to_json(pydict, writepath):
    jstring = json.dumps(pydict, indent=4, allow_nan=True, sort_keys=True)
    f = open(writepath, 'w')
    print >> f, jstring
    f.close()

def save_sparse_hdf5(matrix, prefix, fname):
    """ matrix: sparse matrix
    prefix: prefix of dataset
    fname : name of h5py file where matrix will be saved
    """
    assert matrix.__class__==scipy.sparse.csc.csc_matrix,'Expecting csc/csr, got %s' % matrix.__class__ #matrix.__class__==scipy.sparse.csr.csr_matrix or
    with h5py.File(fname,mode='a') as f:
        for info in ['data','indices','indptr','shape']:
            key = '%s_%s'%(prefix,info)
            try:
                data = getattr(matrix, info)
            except:
                assert False,'Expecting attribute '+info+' in matrix'
            """
            For empty arrays, data, indicies and indptr will be []
            To deal w/ this use np.nan in its place
            """
            if len(data)==0:
                f.create_dataset(key, data=np.array([np.nan]))
            else:
                f.create_dataset(key, data=data)
        key = prefix+'_type'
        val = matrix.__class__.__name__
        f.attrs[key] = np.string_(val)

def load_sparse_mat(prefix, fname):
    with h5py.File(fname, mode='r') as f:
        pars = []
        for par in ('data', 'indices', 'indptr', 'shape'):
            key = '%s_%s'%(prefix,par)
            #print key
            #print f[key]
            pars.append(f[key].value)
            #pars.append(getattr(f, '%s_%s' % (prefix, par)).read())
            #pars.append(f['/'.join([prefix, par])prefix, par))
    m = scipy.sparse.csc_matrix(tuple(pars[:3]), shape=pars[3])
    return m

def loadmat(filename):
    '''
    this function should be called instead of direct spio.loadmat
    as it cures the problem of not properly recovering python dictionaries
    from mat files. It calls the function check keys to cure all entries
    which are still mat-objects
    '''
    data = spio.loadmat(filename, struct_as_record=False, squeeze_me=True)

    return _check_keys(data)

def _check_keys(dict):
    '''
    checks if entries in dictionary are mat-objects. If yes
    todict is called to change them to nested dictionaries
    '''
    for key in dict:
        if isinstance(dict[key], spio.matlab.mio5_params.mat_struct):
            dict[key] = _todict(dict[key])

    return dict

def _todict(matobj):
    '''
    A recursive function which constructs from matobjects nested dictionaries
    '''
    dict = {}
    for strg in matobj._fieldnames:
        elem = matobj.__dict__[strg]
        if isinstance(elem, spio.matlab.mio5_params.mat_struct):
            dict[strg] = _todict(elem)
        elif isinstance(elem,np.ndarray):
            dict[strg] = _tolist(elem)
        else:
            dict[strg] = elem

    return dict

def _tolist(ndarray):
    '''
    A recursive function which constructs lists from cellarrays
    (which are loaded as numpy ndarrays), recursing into the elements
    if they contain matobjects.
    '''
    elem_list = []
    for sub_elem in ndarray:
        if isinstance(sub_elem, spio.matlab.mio5_params.mat_struct):
            elem_list.append(_todict(sub_elem))
        elif isinstance(sub_elem,np.ndarray):
            elem_list.append(_tolist(sub_elem))
        else:
            elem_list.append(sub_elem)

    return elem_list

# -----------------------------------------------------------------------------
# Methods for accessing or changing datafiles and their sources:
# -----------------------------------------------------------------------------
def replace_root(origdir, rootdir, animalid, session):
    orig = origdir.split('/%s/%s' % (animalid, session))[0]
    origdir = origdir.replace(orig, rootdir)
    print "ORIG ROOT: %s" % origdir
    print "NEW ROOT: %s" % origdir
    return origdir

def get_source_info(acquisition_dir, run, process_id):
    info = dict()

    # Set basename for files created containing meta/reference info:
    # -------------------------------------------------------------
    run_info_basename = '%s' % run #functional_dir
    pid_info_basename = 'pids_%s' % run

    # Set paths:
    # -------------------------------------------------------------
    #acquisition_dir = os.path.join(rootdir, animalid, session, acquisition)
    pidinfo_path = os.path.join(acquisition_dir, run, 'processed', '%s.json' % pid_info_basename)
    runmeta_path = os.path.join(acquisition_dir, run, '%s.json' % run)

    # Load run meta info:
    # -------------------------------------------------------------
    with open(runmeta_path, 'r') as r:
        runmeta = json.load(r)

    # Load PID:
    # -------------------------------------------------------------
    with open(pidinfo_path, 'r') as f:
        pdict = json.load(f)

    if len(process_id) == 0 and len(pdict.keys()) > 0:
        process_id = pdict.keys()[0]

    PID = pdict[process_id]

    mc_sourcedir = PID['PARAMS']['motion']['destdir']
    mc_evaldir = '%s_evaluation' % mc_sourcedir
    print "Writing MC EVAL results to: %s" % mc_evaldir
    if not os.path.exists(mc_evaldir):
        os.makedirs(mc_evaldir)

    # Get correlation of MEAN image (mean slice across time) to reference:
    if PID['PARAMS']['motion']['correct_motion'] is True:
        ref_filename = 'File%03d' % PID['PARAMS']['motion']['ref_file']
        ref_channel = 'Channel%02d' % PID['PARAMS']['motion']['ref_channel']
    else:
        ref_filename = 'File001'
        ref_channel = 'Channel01'

    # Create dict to pass around to methods
    info['process_dir'] = PID['DST']
    info['source_dir'] = mc_sourcedir
    info['output_dir'] = mc_evaldir
    info['ref_filename'] = ref_filename
    info['ref_channel'] = ref_channel
    info['d1'] = runmeta['lines_per_frame']
    info['d2'] = runmeta['pixels_per_line']
    info['d3'] = len(runmeta['slices'])
    info['T'] = runmeta['nvolumes']
    info['ntiffs'] = runmeta['ntiffs']

    return info

def get_tiff_paths(rootdir='', animalid='', session='', acquisition='', run='', tiffsource=None, sourcetype=None, auto=False):

    tiffpaths = []

    rundir = os.path.join(rootdir, animalid, session, acquisition, run)
    processed_dir = os.path.join(rundir, 'processed')

    if tiffsource is None:
        while True:
            if auto is True:
                tiffsource = 'raw'
                break
            tiffsource_idx = raw_input('No tiffsource specified. Enter <R> for raw, or <P> for processed: ')
            processed_dirlist = sorted([p for p in os.listdir(processed_dir) if os.path.isdir(os.path.join(processed_dir, p))], key=natural_keys)
            if len(processed_dirlist) == 0 or tiffsource_idx == 'R':
                tiffsource = 'raw'
                if len(processed_dirlist) == 0:
                    print "No processed dirs... Using raw."
                confirm_tiffsource = raw_input('Press <Y> to use raw.')
                if confirm_tiffsource == 'Y':
                    break
            elif len(processed_dirlist) > 0:
                for pidx, pfolder in enumerate(sorted(processed_dirlist, key=natural_keys)):
                    print pidx, pfolder
                tiffsource_idx = int(input("Enter IDX of processed source to use: "))
                tiffsource = processed_dirlist[tiffsource_idx]
                confirm_tiffsource = raw_input('Tiffs are %s? Press <Y> to confirm. ' % tiffsource)
                if confirm_tiffsource == 'Y':
                    break

    if 'processed' in tiffsource:
        process_id_dirs = [t for t in os.listdir(processed_dir) if tiffsource in t and os.path.isdir(os.path.join(processed_dir, t))]
        assert len(process_id_dirs) == 1, "More than 1 specified processed dir found!"
        tiffsource_name = process_id_dirs[0]
        tiff_parent = os.path.join(processed_dir, tiffsource_name)
    else:
        raw_dirs = [t for t in os.listdir(rundir) if tiffsource in t and os.path.isdir(os.path.join(rundir, t))]
        assert len(raw_dirs) == 1, "More than 1 RAW tiff dir found..."
        tiffsource_name = raw_dirs[0]
        tiff_parent = os.path.join(rundir, tiffsource_name)

    print "Using tiffsource:", tiffsource_name

    if sourcetype is None:
        while True:
            if auto is True or tiffsource == 'raw':
                sourcetype = 'raw'
                break
            print "Specified PROCESSED tiff source, but not process type."
            process_id_dir = os.path.join(rundir, 'processed', tiffsource)
            processed_typlist = sorted([t for t in os.listdir(process_id_dir) if os.path.isdir(os.path.join(process_id_dir, t))], key=natural_keys)
            for tidx, tname in enumerate(processed_typlist):
                print tidx, tname
            sourcetype_idx = int(input('Enter IDX of processed dir to use: '))
            sourcetype = processed_typlist[sourcetype_idx]
            confirm_sourcetype = raw_input('Tiffs are from %s? Press <Y> to confirm. ' % sourcetype)
            if confirm_sourcetype == 'Y':
                break

    if 'processed' in tiffsource_name:
        source_type_dirs = [s for s in os.listdir(tiff_parent) if sourcetype in s and os.path.isdir(os.path.join(tiff_parent, s)) and len(s.split('_'))<=2]
        assert len(source_type_dirs) == 1, "More than 1 specified source [%s] found..." % sourcetype
        sourcetype_name = source_type_dirs[0]
        tiff_path = os.path.join(tiff_parent, sourcetype_name)
    else:
        tiff_path = tiff_parent

    print "Looking for tiffs in tiff_path: %s" % tiff_path
    tiff_fns = [t for t in os.listdir(tiff_path) if t.endswith('tif')]
    tiffpaths = sorted([os.path.join(tiff_path, fn) for fn in tiff_fns], key=natural_keys)
    print "Found %i TIFFs." % len(tiff_fns)

    return tiffpaths

def convert_bytes(num):
    """
    this function will convert bytes to MB.... GB... etc
    """
    for x in ['bytes', 'KB', 'MB', 'GB', 'TB']:
        if num < 1024.0:
            return "%3.1f %s" % (num, x)
        num /= 1024.0

def get_file_size(file_path):
    """
    this function will return the file size
    """
    if os.path.isfile(file_path):
        file_info = os.stat(file_path)
        return convert_bytes(file_info.st_size)

def change_permissions_recursive(path, mode):
    for root, dirs, files in os.walk(path, topdown=False):
        #for dir in [os.path.join(root,d) for d in dirs]:
            #os.chmod(dir, mode)
        for file in [os.path.join(root, f) for f in files]:
            os.chmod(file, mode)

def hash_file_read_only(fpath, hashtype='sha1'):
    hashid = hash_file(fpath, hashtype=hashtype)
    hashed_fpath = "%s_%s%s" % (os.path.splitext(fpath)[0], hashid, os.path.splitext(fpath)[1])
    shutil.move(fpath, hashed_fpath)
    print "Hashed file: %s" % hashed_fpath

    change_permissions_recursive(hashed_fpath, S_IREAD|S_IRGRP|S_IROTH)
    print "Set READ-ONLY."

    return hashed_fpath

def hash_file(fpath, hashtype='sha1'):

    BLOCKSIZE = 65536
    if hashtype=='md5':
        hasher = hashlib.md5()
    else:
        hasher = hashlib.sha1()

    with open(fpath, 'rb') as afile:
        buf = afile.read(BLOCKSIZE)
        while len(buf) > 0:
            hasher.update(buf)
            buf = afile.read(BLOCKSIZE)

    return hasher.hexdigest()[0:6]


# -----------------------------------------------------------------------------
# General TIFF processing methods:
# -----------------------------------------------------------------------------
def interleave_tiffs(source_dir, write_dir, runinfo_path):
    '''
    source_dir (str) : path to folder containing tiffs to interleave
    runinfo_path (str) : path to .json contaning run meta info
    write_dir (str) : path to save interleaved tiffs to
    '''
    with open(runinfo_path, 'r') as f:
        runinfo = json.load(f)
    nfiles = runinfo['ntiffs']
    nchannels = runinfo['nchannels']
    nslices = len(runinfo['slices'])
    nvolumes = runinfo['nvolumes']
    ntotalframes = nslices * nvolumes * nchannels
    basename = runinfo['base_filename']

    if not os.path.exists(write_dir):
        os.makedirs(write_dir)
    print "Writing INTERLEAVED tiffs to:", write_dir

    tiffs = sorted([t for t in os.listdir(source_dir) if t.endswith('tif')], key=natural_keys)
    for fidx in range(nfiles):
        print "Interleaving file %i of %i." % (int(fidx+1), nfiles)
        curr_file = 'File%03d' % int(fidx+1)
        interleaved_fn = "{basename}_{currfile}.tif".format(basename=basename, currfile=curr_file)
        print "New tiff name:", interleaved_fn
        curr_file_fns = [t for t in tiffs if curr_file in t]
        sample = tf.imread(os.path.join(source_dir, curr_file_fns[0]))
        print "Found %i tiffs for current file." % len(curr_file_fns)
        stack = np.empty((ntotalframes, sample.shape[1], sample.shape[2]), dtype=sample.dtype)
        for fn in curr_file_fns:
            curr_tiff = tf.imread(os.path.join(source_dir, fn))
            sl_idx = int(fn.split('Slice')[1][0:2]) - 1
            ch_idx = int(fn.split('Channel')[1][0:2]) - 1
            slice_indices = np.arange((sl_idx*nchannels)+ch_idx, ntotalframes)
            idxs = slice_indices[::(nslices*nchannels)]
            stack[idxs,:,:] = curr_tiff

        tf.imsave(os.path.join(write_dir, interleaved_fn), stack)

def deinterleave_tiffs(source_dir, write_dir, runinfo_path):
    '''
    source_dir (str) : path to folder containing interleaved tiffs
    write_dir (str): path to save deinterleaved tiffs to (sorted by Channel, File)
    runinfo_path (str) : path to .json containing meta info about run
    '''
    with open(runinfo_path, 'r') as f:
        runinfo = json.load(f)
    nfiles = runinfo['ntiffs']
    nchannels = runinfo['nchannels']
    nslices = len(runinfo['slices'])
    nvolumes = runinfo['nvolumes']
    ntotalframes = nslices * nvolumes * nchannels
    basename = runinfo['base_filename']

    if not os.path.exists(write_dir):
        os.makedirs(write_dir)

    print "Writing DEINTERLEAVED tiffs to:", write_dir

    tiffs = sorted([t for t in os.listdir(source_dir) if t.endswith('tif')], key=natural_keys)
    good_to_go = True
    if not len(tiffs) == nfiles:
        print "**WARNING*********************"
        print "Mismatch in num tiffs. Expected %i files, found %i tiffs in dir:\n%s" % (ntiffs, len(tiffs), source_dir)
        #good_to_go = False
    if good_to_go:
        # Load in each TIFF and deinterleave:
        for fidx,filename in enumerate(sorted(tiffs, key=natural_keys)):
            print "Deinterleaving File %i of %i [%s]" % (int(fidx+1), nfiles, filename)
            stack = tf.imread(os.path.join(source_dir, filename))
            print "Size:", stack.shape
            curr_file = "File%03d" % int(fidx+1)
            for ch_idx in range(nchannels):
                curr_channel = "Channel%02d" % int(ch_idx+1)
                for sl_idx in range(nslices):
                    curr_slice = "Slice%02d" % int(sl_idx+1)
                    frame_idx = ch_idx + sl_idx*nchannels
                    slice_indices = np.arange(frame_idx, ntotalframes, (nslices*nchannels))
                    print "nslices:", len(slice_indices)
                    curr_slice_fn = "{basename}_{currslice}_{currchannel}_{currfile}.tif".format(basename=basename, currslice=curr_slice, currchannel=curr_channel, currfile=curr_file)
                    tf.imsave(os.path.join(write_dir, curr_slice_fn), stack[slice_indices, :, :])

def sort_deinterleaved_tiffs(source_dir, runinfo_path):
    '''
    source_dir (str) : path to folder containing deinterleaved tiffs
    runinfo_path (str) : path to .json containing meta info about run
    '''
    with open(runinfo_path, 'r') as f:
        runinfo = json.load(f)
    nfiles = runinfo['ntiffs']
    nchannels = runinfo['nchannels']
    nslices = len(runinfo['slices'])
    nvolumes = runinfo['nvolumes']
    ntotalframes = nslices * nvolumes * nchannels
    basename = runinfo['base_filename']

    channel_names = ['Channel%02d' % int(ci + 1) for ci in range(nchannels)]
    file_names = ['File%03d' % int(fi + 1) for fi in range(nfiles)]
    print "Expected channels:", channel_names
    print "Expected file:", file_names

    # Check that no "vis" duplicate files are in source_dir:
    vis_tiffs = sorted([t for t in os.listdir(source_dir) if 'vis_' in t and t.endswith('tif')], key=natural_keys)
    if len(vis_tiffs) > 0:
        print "Found tiffs with matching vis_ files."
        visible_dir = os.path.join(source_dir, 'visible')
        if not os.path.exists(visible_dir):
            os.makedirs(visible_dir)
        for vtiff in vis_tiffs:
            shutil.move(os.path.join(source_dir, vtiff), os.path.join(visible_dir, vtiff))
        print "Moved set of VISIBLE tiff duplicates to:", visible_dir


    all_tiffs = sorted([t for t in os.listdir(source_dir) if t.endswith('tif')], key=natural_keys)
    #print "Tiffs to deinterleave:", all_tiffs
    expected_ntiffs = nfiles * nchannels * nslices
    good_to_go = True
    if not len(all_tiffs) == expected_ntiffs:
        print "**WARNING*********************"
        print "Mismatch in tiffs found (%i) and expected n tiffs (%i)." % (len(all_tiffs), expected_ntiffs)
        #good_to_go = False # sometimes we do a subset of session files
    else:
        print "Found %i TIFFs in source:" % len(all_tiffs), source_dir
        print "Expected n tiffs:", expected_ntiffs

    if good_to_go is True:
        for channel_name in channel_names:
            print "Sorting %s" % channel_name
            tiffs_by_channel = [t for t in all_tiffs if channel_name in t]
            channel_dir = os.path.join(source_dir, channel_name)
            if not os.path.exists(channel_dir):
                os.makedirs(channel_dir)
            for ch_tiff in tiffs_by_channel:
                shutil.move(os.path.join(source_dir, ch_tiff), os.path.join(channel_dir, ch_tiff))
            for file_name in file_names:
                print "Sorting %s" % file_name
                tiffs_by_file = [t for t in tiffs_by_channel if file_name in t]
                print "Curr file tiffs:", tiffs_by_file
                file_dir = os.path.join(channel_dir, file_name)
                print "File dir:", file_dir
                if not os.path.exists(file_dir):
                    os.makedirs(file_dir)
                for fi_tiff in tiffs_by_file:
                    shutil.move(os.path.join(channel_dir, fi_tiff), os.path.join(file_dir, fi_tiff))
    print "Done organizing tiffs."


def zproj_tseries(source_dir, runinfo_path, zproj_type='mean', write_dir=None):
    '''
    source_dir (str) : path to folder containing tiffs to deinterleave and z-project
    runinfo_path (str) : path to .json contaning run meta info
    write_dir (str) : path to save averaged slices to
    '''
    with open(runinfo_path, 'r') as f:
        runinfo = json.load(f)
    nfiles = runinfo['ntiffs']
    nchannels = runinfo['nchannels']
    nslices = len(runinfo['slices'])
    nvolumes = runinfo['nvolumes']
    ntotalframes = nslices * nvolumes * nchannels
    basename = runinfo['base_filename']

    # Default write-dir should be source_dir_<projectiontype>_slices
    if write_dir is None:
        write_dir = source_dir + '_%s_slices' % zproj_type
    if not os.path.exists(write_dir):
        os.makedirs(write_dir)
    print "Writing AVERAGED SLICES to:", write_dir

    tiffs = sorted([t for t in os.listdir(source_dir) if t.endswith('tif')], key=natural_keys)
    print tiffs
    filenames = ['File%03d' % int(i+1) for i in range(len(tiffs))] #nfiles)]
    for fi, (tfn, fname) in enumerate(zip(sorted(tiffs, key=natural_keys), sorted(filenames, key=natural_keys))):
        filenum = int(fi + 1)
	print fi, fname, tfn
        #tiff_fns = [t for t in tiffs if fname in t]
        #tfn = tiff_fns[0]
        currtiff = tf.imread(os.path.join(source_dir, tfn))
        nslices_actual = currtiff.shape[0]/(nchannels*nvolumes)
	ndiscard = nslices_actual - nslices
        if currtiff.shape[0] == nchannels*(nslices+ndiscard)*nvolumes:
            for ch in range(nchannels):
                channelnum = int(ch+1)
                ch_tiff = currtiff[ch::nchannels]
                for sl in range(nslices):
                    slicenum = int(sl+1)
                    sl_tiff = ch_tiff[sl::(nslices+ndiscard)]
		    print "Slice tiff shape:", sl_tiff.shape
                    if zproj_type == 'mean' or zproj_type == 'average':
                        zprojslice = np.mean(sl_tiff, axis=0).astype(currtiff.dtype)
                    elif zproj_type == 'std':
                        zprojslice = np.std(sl_tiff, axis=0).astype(currtiff.dtype)
                    curr_slice_fn = default_filename(slicenum, channelnum, filenum, acq=None, run=None)
                    tf.imsave(os.path.join(write_dir, '%s_%s.tif' % (zproj_type, curr_slice_fn)), zprojslice)

                    # Save visible too:
                    byteimg = img_as_ubyte(zprojslice)
                    zproj_vis = exposure.rescale_intensity(byteimg, in_range=(byteimg.min(), byteimg.max()))
                    tf.imsave(os.path.join(write_dir, 'vis_%s_%s.tif' % (zproj_type, curr_slice_fn)), zproj_vis)

                    print "Finished zproj for %s, Slice%02d, Channel%02d." % (fname, int(sl+1), int(ch+1))
        else:
            print "Loaded tiff shape does not match dims expected:", os.path.join(source_dir, tfn)
            print "nchannels: %i, nslices: %i, ndiscard: %i, nvolumes: %i" % (nchannels, nslices, ndiscard, nvolumes)
    # Sort separated tiff slice images:
    sort_deinterleaved_tiffs(write_dir, runinfo_path)  # Moves all 'vis_' files to separate subfolder 'visible'
    #sort_deinterleaved_tiffs(os.path.join(write_dir, 'visible'), runinfo_path)
