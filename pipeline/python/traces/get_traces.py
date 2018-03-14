#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Extracted time courses using a set of trace params (TID) defined with set_trace_params.py

Outputs:

    a.  Images of masks for each tif file:

        <TRACEID_DIR>/figures/roi_FILEXXX_SliceXX_<RID_NAME>_<RID_HASH>.png
        -- Masks overlaid on zprojected reference slice img with labeled rois.

    b. HDF5 files containing extracted traces from specified ROI set:

        <TRACEID_DIR>/files/FileXXX_rawtraces_<TRACEID_HASH>.hdf5
        -- Extracted raw traces using specified trace params (and specified ROI set)-- this means, .tif files excluded in ROI set are excluded here, too.
        -- File hierarchy is:

        /FileXXX    - group
            - attrs:
                source_file        : TIF file path from which traces were extracted
                file_id            : filename (i.e., File006, for ex.)
                dims               : (array) dimension as d1 x d2 x nslices x nframes
                masks              : <SESSION_DIR>/ROIs/<RID_DIR>/masks.hdf5 <-- standardized mask file (TODO:  make sure this is always produced)

            /SliceXX - group
                /traces - group
                    /raw - dataset
                        [Txnrois] array
                        - atttrs:
                            nframes : T (num of frames in file)
                            dims    : original dimensions of movie for reshaping (d1xd2)
                    /denoised_nmf - dataset
                        [Txnrois] array
                        - attrs:
                            nb      :  number of background components (relevant only for cNMF)
                            nr      :  number of rois

                /masks - dataset
                    [d1xd2xnrois] array
                    - attrs:
                        roi_id         : RID name,
                        rid_hash       : RID hash,
                        roi_type       : roi type,
                        nr             : num rois in set,
                        nb             : num background components, if any
                        src_roi_idxs   : original indices of rois in set (some ROIs are subsets of some other ROI set)

                /zproj - dataset
                    [d1xd2] zprojected image
                    - attrs:
                        img_source     : file path to zprojected reference image

                /frames_tsec - dataset
                    [T,] array -- corresponding time in secs for each frame in timecourse
                    --> Note:  this info is extracted from SI META info (preprocessing/get_scanimage_data.py), and saved to run meta info
                    -- runmeta info is saved to:  <RUN_DIR>/<RUN_NAME>.json
                    -- frame times and indices should be re-indexed based on discard frames/skipped frames

    c.  Traces separated for each ROI:

        <TRACEID_DIR>/roi_timecourses_YYYYMMDD_HH_MM_SS_<filehash>.hdf5
        -- Trace arrays split up by ROI.
        -- File hierarchy is:

        /roi00001 - Group (length-5 name of ROI in set, 1-indexed; may include background components as 'bg01', 'bg02', etc.)
            - attrs:
                slice        :  slice on which current roi (or com) is
                roi_img_path :  source of zprojected slice image
                id_in_set    :  ROI id in current ROI set (should match Group name) -- relative to entire set (across slices, too)
                id_in_src    :  ROI id in source from which ROI was originally created (can be different than id_in_set)
                idx_in_slice :  index of ROI in current slice (in case multiple slices exist)

            /mask - dataset
                [d1xd2] array
                - attrs:
                    slice         :  'SliceXX'
                    is_background :  (bool) whether mask image is background (really only relevant for cNMF rois)

            /timecourse - Group
                /raw - dataset
                    [T,] timecourse of roi
                    - attrs:
                        source_file:  path to file from which trace is extracted
                /denoised_nmf - dataset
                    [T,] timecourse of roi
                    - attrs:
                        source_file:  path to file from which trace is extracted

Created on Tue Dec 12 11:57:24 2017

@author: julianarhee
"""

import matplotlib
matplotlib.use('Agg')
import os
import sys
import h5py
import json
import re
import datetime
import optparse
import pprint
import traceback
import time
import skimage
import shutil
import tifffile as tf
import pylab as pl
import numpy as np
import cPickle as pkl
from pipeline.python.utils import natural_keys, hash_file_read_only, load_sparse_mat, print_elapsed_time, hash_file, replace_root
from pipeline.python.set_trace_params import post_tid_cleanup
from pipeline.python.rois.utils import get_info_from_tiff_dir
from pipeline.python.traces.utils import get_frame_info, get_metric_set
from pipeline.python.paradigm import align_acquisition_events as acq
pp = pprint.PrettyPrinter(indent=4)

#%%

def load_TID(run_dir, trace_id, auto=False):
    run = os.path.split(run_dir)[-1]
    trace_dir = os.path.join(run_dir, 'traces')
    tmp_tid_dir = os.path.join(trace_dir, 'tmp_tids')
    tracedict_path = os.path.join(trace_dir, 'traceids_%s.json' % run)
    try:
        print "Loading params for TRACE SET, id %s" % trace_id
        with open(tracedict_path, 'r') as f:
            tracedict = json.load(f)
        TID = tracedict[trace_id]
        pp.pprint(TID)
    except Exception as e:
        print "No TRACE SET entry exists for specified id: %s" % trace_id
        print "TRACE DIR:", tracedict_path
        try:
            print "Checking tmp trace-id dir..."
            if auto is False:
                while True:
                    tmpfns = [t for t in os.listdir(tmp_tid_dir) if t.endswith('json')]
                    for tidx, tidfn in enumerate(tmpfns):
                        print tidx, tidfn
                    userchoice = raw_input("Select IDX of found tmp trace-id to view: ")
                    with open(os.path.join(tmp_tid_dir, tmpfns[int(userchoice)]), 'r') as f:
                        tmpTID = json.load(f)
                    print "Showing tid: %s, %s" % (tmpTID['trace_id'], tmpTID['trace_hash'])
                    pp.pprint(tmpTID)
                    userconfirm = raw_input('Press <Y> to use this trace ID, or <q> to abort: ')
                    if userconfirm == 'Y':
                        TID = tmpTID
                        break
                    elif userconfirm == 'q':
                        break
        except Exception as e:
            traceback.print_exc()
            print "---------------------------------------------------------------"
            print "No tmp trace-ids found either... ABORTING with error:"
            print e
            print "---------------------------------------------------------------"

    return TID

#%%
def get_mask_info(mask_path, ntiffs=None):
    maskinfo = dict()
    try:
        maskfile = h5py.File(mask_path, "r")
        is_3D = bool(maskfile.attrs['is_3D'])

        # Get files for which there are ROIs in this set:
        maskfiles = maskfile.keys()
        print "MASK FILES:", len(maskfiles)
        if len(maskfiles) == 1:
            #ntiffs = maskfile.attrs['ntiffs_in_set']
            filenames = sorted(['File%03d' % int(i+1) for i in range(ntiffs)], key=natural_keys)
            ref_file = maskfiles[0]
            print "Using reference file %s on %i total tiffs." % (ref_file, len(filenames))
            single_reference = True
        else:
            filenames = maskfile.keys()
            single_reference = False
            ref_file = None #RID['PARAMS']['options']['ref_file']

        # Check if masks are split up by slices: (Matlab, manual2D methods are diff)
        if type(maskfile[maskfiles[0]]['masks']) == h5py.Dataset:
            slice_masks = False
        else:
            slice_keys = [s for s in maskfile[maskfiles[0]]['masks'].keys() if 'Slice' in s]
            if len(slice_keys) > 0:
                slice_masks = True
            else:
                slice_masks = False

        # Get slices for which there are ROIs in this set:
        if slice_masks:
            roi_slices = sorted([str(s) for s in maskfile[maskfiles[0]]['masks'].keys()], key=natural_keys)
        else:
            roi_slices = sorted(["Slice%02d" % int(s+1) for s in range(nslices)], key=natural_keys)
    except Exception as e:
        traceback.print_exc()
        print "Error loading mask info..."
        print "Mask path was: %s" % mask_path
    #finally:
        #maskfile.close()

    maskinfo['filenames'] = filenames
    maskinfo['ref_file'] = ref_file
    maskinfo['is_single_reference'] = single_reference
    maskinfo['is_3D'] = is_3D
    maskinfo['is_slice_format'] = slice_masks
    maskinfo['roi_slices'] = roi_slices
    maskinfo['filepath'] = mask_path

    return maskinfo

#%%
def get_masks(maskinfo, RID, normalize_rois=False, notnative=False, rootdir='', animalid='', session=''):
    '''
    This function takes a masks.hdf5 file and formats it into a dict that standardizes how
    mask arrays are called. This was a tmp fix to deal with the fact that
        - ROI types differ in saving/indexing ROIs by slice or across the whole volume (only relevant for 3D)
        - if ROI type only uses a single reference (manual, for ex.), we want to apply those ROIs to all other files
        - cNMF trace extraction offers non-raw traces, so just bring that along at this step

    Save MASKS.pkl at end.
    This only needs to be done once, unless create_new = True (i.e., if re-doing masks prior to extracting traces).
    '''

    MASKS = dict()

    maskfile = h5py.File(maskinfo['filepath'], "r")
    MASKS['original_source'] = maskinfo['filepath']
    for fidx, curr_file in enumerate(maskinfo['filenames']):
        MASKS[curr_file] = dict()

        if maskinfo['is_single_reference'] is True:  # Load current file zproj image to draw ROIs
            maskfile_key = maskinfo['ref_file']
        else:
            maskfile_key = curr_file

        if 'source' not in maskfile[maskfile_key].attrs.keys():
            zproj_source_dir = os.path.split(maskfile[maskfile_key]['masks'].attrs['source'])[0]  # .../mean_slices_dir/Channel01/File00X
        else:
            zproj_source_dir = os.path.split(maskfile[maskfile_key].attrs['source'])[0]
        zproj_dir = os.path.join(zproj_source_dir, curr_file)

        # Check root:
        if rootdir not in zproj_dir:
            print "Replacing root..."
            zproj_dir = replace_root(zproj_dir, rootdir, animalid, session)

        # Make sure all masks are saved by file, slice:
        for sidx, curr_slice in enumerate(maskinfo['roi_slices']):

            MASKS[curr_file][curr_slice] = dict()

            # Get average image:
            if maskinfo['is_single_reference'] is True:
                if curr_file == maskfile_key and maskinfo['is_slice_format']: #slice_masks:
                    avg = np.array(maskfile[maskfile_key]['zproj_img'][curr_slice]).T
                    MASKS[curr_file][curr_slice]['zproj_source'] = maskfile[maskfile_key]['zproj_img'][curr_slice].attrs['source_file']
                else:
                    zproj_img_fn = [m for m in os.listdir(zproj_dir) if curr_slice in m][0]
                    zproj_img_path = os.path.join(zproj_dir, zproj_img_fn)
                    avg = tf.imread(zproj_img_path)
                    MASKS[curr_file][curr_slice]['zproj_source'] = zproj_img_path
            else:
                if maskinfo['is_slice_format']: #slice_masks:
                    avg = np.array(maskfile[maskfile_key]['zproj_img'][curr_slice]).T
                    MASKS[curr_file][curr_slice]['zproj_source'] = maskfile[maskfile_key]['zproj_img'][curr_slice].attrs['source_file']
                else:
                    avg = np.array(maskfile[maskfile_key]['zproj_img'])
                    MASKS[curr_file][curr_slice]['zproj_source'] = maskfile[maskfile_key].attrs['source']

            MASKS[curr_file][curr_slice]['zproj_img'] =  avg
            if maskinfo['is_slice_format']: #slice_masks:
                MASKS[curr_file][curr_slice]['src_roi_idxs'] = maskfile[maskfile_key]['masks'][curr_slice].attrs['src_roi_idxs']
            else:
                MASKS[curr_file][curr_slice]['src_roi_idxs'] = maskfile[maskfile_key]['masks'].attrs['src_roi_idxs']

            d1,d2 = avg.shape
            d = d1*d2

            # Plot labeled ROIs on avg img:
            curr_rois = sorted(["roi%05d" % int(ridx+1) for ridx in range(len(MASKS[curr_file][curr_slice]['src_roi_idxs']))], key=natural_keys)

            # Check if extra backround:
            if 'background' in maskfile[maskfile_key]['masks'].attrs.keys():
                nb = maskfile[maskfile_key]['masks'].attrs['background']
                #curr_rois = curr_rois[0:-1*nb]
            else:
                nb = 0
            nrois = len(curr_rois)
            MASKS[curr_file][curr_slice]['nb'] = nb
            MASKS[curr_file][curr_slice]['nr'] = nrois - nb

            # Create maskarray:
            print "Creating mask array: %i ROIs on %s, %s" % (len(curr_rois), curr_file, curr_slice)
            maskarray = np.empty((d, nrois))
            maskarray_roi_ids = []
            for ridx, roi in enumerate(curr_rois):
                if maskinfo['is_slice_format']: #slice_masks:
                    masktmp = np.array(maskfile[maskfile_key]['masks'][curr_slice]).T[:,:,ridx] # T is needed for MATLAB masks... (TODO: check roi_blobs)
                else:
                    if len(maskinfo['roi_slices']) > 1:
                        masktmp = maskfile[maskfile_key]['masks'][:,:,sidx,ridx]
                    else:
                        masktmp = maskfile[maskfile_key]['masks'][:,:,ridx]

                # Normalize by size:
                masktmp = np.reshape(masktmp, (d,), order='C')
                if normalize_rois is True:
                    npixels = len(np.nonzero(masktmp)[0])
                    maskarray[:, ridx] = masktmp/npixels
                else:
                    maskarray[:, ridx] = masktmp
                maskarray_roi_ids.append(roi)

            MASKS[curr_file][curr_slice]['mask_array'] = maskarray
            MASKS[curr_file][curr_slice]['rois'] = curr_rois

            # CHeck if have nmf traces:
            if 'Ab_data' in maskfile[maskfile.keys()[0]].keys():
                Ab = load_sparse_mat('%s/Ab' % curr_file, maskinfo['filepath']).todense()
                Cf = load_sparse_mat('%s/Cf' % curr_file, maskinfo['filepath']).todense()
                MASKS[curr_file][curr_slice]['Ab'] = Ab
                MASKS[curr_file][curr_slice]['Cf'] = Cf

    maskfile.close()

    return MASKS #, curr_rois

#%%
def plot_roi_masks(TID, RID, mask_figdir='/tmp', rootdir=''):
    '''
    This also only needs to be done once, unless create_new = True or incorrect
    number of mask images found in <TRACEID_DIR>/figures/masks/.

    It's a little slow..

    '''

    maskdict_path = os.path.join(TID['DST'], 'MASKS.pkl')
    if rootdir not in maskdict_path:
        session_dir = RID['DST'].split('/ROIs/')[0]
        info = get_info_from_tiff_dir(TID['SRC'], session_dir)
        maskdict_path = replace_root(maskdict_path, rootdir, info['animalid'], info['session'])

    with open(maskdict_path, 'rb') as f:
        MASKS = pkl.load(f)
    f.close()
    print "Plotting masks for %i files." % len(MASKS.keys())
    filenames = [k for k in MASKS.keys() if 'File' in k]
    for curr_file in sorted(filenames, key=natural_keys): #sorted(MASKS.keys(), key=natural_keys):
        for curr_slice in sorted(MASKS[curr_file].keys(), key=natural_keys):
            curr_rois = MASKS[curr_file][curr_slice]['rois']
            nrois = len(curr_rois)

            avg = MASKS[curr_file][curr_slice]['zproj_img']
            dims = avg.shape

            fig = pl.figure()
            ax = fig.add_subplot(1,1,1)
            p2, p98 = np.percentile(avg, (2, 99.98))
            avgimg = skimage.exposure.rescale_intensity(avg, in_range=(p2, p98)) #avg *= (1.0/avg.max())
            ax.imshow(avgimg, cmap='gray')

            print "Plotting mask array: %i ROIs on %s, %s" % (len(curr_rois), curr_file, curr_slice)

            nb = MASKS[curr_file][curr_slice]['nb']

            bgidx = 0
            for ridx in range(nrois):
                masktmp = np.reshape(MASKS[curr_file][curr_slice]['mask_array'][:, ridx], dims, order='C')
                msk = masktmp.copy()
                msk[msk==0] = np.nan

                if (nb > 0) and (ridx >= (nrois-nb)):
                    bgidx += 1
                    bgfig = pl.figure()
                    bgax = bgfig.add_subplot(1,1,1)
                    bgax.imshow(avg, cmap='gray')
                    bgax.imshow(msk, interpolation='None', alpha=0.3, cmap=pl.cm.hot)
                    pl.title('background %i' % bgidx)
                    pl.savefig(os.path.join(mask_figdir, 'bg%i_%s_%s_%s_%s.png' % (bgidx, curr_file, curr_slice, RID['roi_id'], RID['rid_hash'])))
                    pl.close()
                else:
                    if 'caiman' in RID['roi_type'] or (RID['roi_type']=='coregister' and 'caiman' in RID['PARAMS']['options']['source']['roi_type']):
                        ax.imshow(msk, interpolation='None', alpha=0.2, cmap=pl.cm.hot)
                    else:
                        ax.imshow(msk, interpolation='None', alpha=0.5, cmap=pl.cm.Greens_r)
                    [ys, xs] = np.where(masktmp>0)
                    ax.text(xs[int(round(len(xs)/4))], ys[int(round(len(ys)/4))], str(ridx+1), fontsize=8, weight='light', color='w')
                ax.axis('off')

            pl.savefig(os.path.join(mask_figdir, 'rois_%s_%s_%s_%s.png' % (curr_file, curr_slice, RID['roi_id'], RID['rid_hash'])))
            pl.close()


#%%
# =============================================================================
# Extract ROIs for each specified slice for each file:
# =============================================================================
def apply_masks_to_movies(TID, RID, si_info, output_filedir='/tmp', rootdir=''):
    '''
    For each .tif in this trace id set, load .tif movie and apply masks.
    Save traces as .hdf5 for each .tif file in <TRACEID_DIR>/files/.
    '''
    file_grp = None

    session_dir = RID['DST'].split('/ROIs/')[0]
    info = get_info_from_tiff_dir(TID['SRC'], session_dir)

    nchannels = si_info['nchannels']
    nslices = si_info['nslices']
    nvolumes = si_info['nvolumes']
    frames_tsec = si_info['frames_tsec']

    #roi_slices = maskinfo['roi_slices']
    tiff_dir = TID['SRC']
    if rootdir not in tiff_dir:
        tiff_dir = replace_root(tiff_dir, rootdir, info['animalid'], info['session'])
    tiff_files = sorted([t for t in os.listdir(tiff_dir) if t.endswith('tif')], key=natural_keys)

    print "TID %s -- Applying masks to traces..." % TID['trace_hash']
    t_extract = time.time()

    # Load MASKDICT:
    traceid_dir = TID['DST']
    if rootdir not in traceid_dir:
        traceid_dir = replace_root(traceid_dir, rootdir, info['animalid'], info['session'])

    maskdict_path = os.path.join(traceid_dir, 'MASKS.pkl')
    with open(maskdict_path, 'rb') as f:
        MASKS = pkl.load(f)
    f.close()
    print "Applying masks to %i files." % len(MASKS.keys())
    filenames = [k for k in MASKS.keys() if 'File' in k]
    roi_slices = [k for k in MASKS[filenames[0]].keys() if 'Slice' in k] #maskinfo['roi_slices']

    signal_channel_idx = int(TID['PARAMS']['signal_channel']) - 1 # 0-indexing into tiffs
    file_hashdict = dict()
    try:
        for tfn in tiff_files:

            curr_file = str(re.search(r"File\d{3}", tfn).group())
            if curr_file in TID['PARAMS']['excluded_tiffs']:
                print "***Skipping %s -- excluded from ROI set %s" % (curr_file, RID['roi_id'])
                continue

            print "Extracting traces: %s" % curr_file

            # Create outfile:
            filetrace_fn = '%s_rawtraces_%s.hdf5' % (curr_file, TID['trace_hash'])
            filetrace_filepath = os.path.join(traceid_dir, 'files', filetrace_fn)

            # Load input tiff file:
            print "Reading tiff..."
            currtiff_path = os.path.join(tiff_dir, tfn)
            tiff = tf.imread(currtiff_path)
            T, d1, d2 = tiff.shape
            d = d1*d2
            tiffR = np.reshape(tiff, (T, d), order='C')

            # First get signal channel only:
            tiffR = tiffR[signal_channel_idx::nchannels,:]

            # Apply masks to each slice:
            file_grp = h5py.File(filetrace_filepath, 'w')
            file_grp.attrs['source_file'] = currtiff_path
            file_grp.attrs['file_id'] = curr_file
            file_grp.attrs['dims'] = (d1, d2, nslices, T/nslices)
            file_grp.attrs['mask_sourcefile'] = MASKS['original_source'] #mask_path

            for sl in range(len(roi_slices)):

                curr_slice = 'Slice%02d' % int(roi_slices[sl][5:])
                print "Extracting ROI time course from %s" % curr_slice
                maskarray = MASKS[curr_file][roi_slices[sl]]['mask_array']

                # Get frame tstamps:
                curr_tstamps = np.array(frames_tsec[sl::nslices])

                # Get current frames:
                tiffslice = tiffR[sl::nslices, :]
                tracemat = tiffslice.dot(maskarray)
                dims = (d1, d2, T/nvolumes)

                if curr_slice not in file_grp.keys():
                    slice_grp = file_grp.create_group(curr_slice)
                else:
                    slice_grp = file_grp[curr_slice]

                # Save masks:
                if 'masks' not in slice_grp.keys():
                    mset = slice_grp.create_dataset('masks', maskarray.shape, maskarray.dtype)
                mset[...] = maskarray
                mset.attrs['roi_id'] = str(RID['roi_id'])
                mset.attrs['rid_hash'] = str(RID['rid_hash'])
                mset.attrs['roi_type'] = str(RID['roi_type'])
                mset.attrs['nr'] = MASKS[curr_file][curr_slice]['nr']
                mset.attrs['nb'] = MASKS[curr_file][curr_slice]['nb']
                mset.attrs['src_roi_idxs'] = MASKS[curr_file][curr_slice]['src_roi_idxs']

                # Save zproj img:
                zproj = MASKS[curr_file][curr_slice]['zproj_img']
                if 'zproj' not in slice_grp.keys():
                    zset = slice_grp.create_dataset('zproj', zproj.shape, zproj.dtype)
                zset[...] = zproj
                zset.attrs['img_source'] = MASKS[curr_file][curr_slice]['zproj_source']

                # Save fluor trace:
                if 'rawtraces' not in slice_grp.keys():
                    tset = slice_grp.create_dataset('/'.join(['traces', 'raw']), tracemat.shape, tracemat.dtype)
                tset[...] = tracemat
                tset.attrs['nframes'] = tracemat.shape[0]
                tset.attrs['dims'] = dims

                # Save tstamps:
                if 'frames_tsec' not in slice_grp.keys():
                    fset = slice_grp.create_dataset('frames_tsec', curr_tstamps.shape, curr_tstamps.dtype)
                fset[...] = curr_tstamps

                if 'Ab' in MASKS[curr_file][curr_slice].keys():
                    Ab = MASKS[curr_file][curr_slice]['Ab']
                    Cf = MASKS[curr_file][curr_slice]['Cf']
                    extracted_traces = Ab.T.dot(Ab.dot(Cf))
                    extracted_traces = np.array(extracted_traces.T) # trans to get same format as other traces (NR x Tpoints)
                    ext = slice_grp.create_dataset('/'.join(['traces', 'denoised_nmf']), extracted_traces.shape, extracted_traces.dtype)
                    ext[...] = extracted_traces
                    ext.attrs['nb'] = MASKS[curr_file][curr_slice]['nb']
                    ext.attrs['nr'] = MASKS[curr_file][curr_slice]['nr']

            # Create hash of current raw tracemat:
            rawfile_hash = hash_file(filetrace_filepath)
            file_hashdict[os.path.splitext(filetrace_fn)[0]] = rawfile_hash
    except Exception as e:
        print "--- TID %s: Error extracting traces from file %s ---" % (TID['trace_hash'], curr_file)
        traceback.print_exc()
        print "---------------------------------------------------------------"
    finally:
        if file_grp is not None:
            file_grp.close()
        #maskfile.close()

    with open(os.path.join(traceid_dir, 'files', 'filetrace_info_%s.json' % TID['trace_hash']), 'w') as f:
        json.dump(file_hashdict, f, indent=4, sort_keys=True)

    #%
    print "TID %s -- Finished compiling trace arrays across files" % TID['trace_hash']
    print_elapsed_time(t_extract)
    print "-----------------------------------------------------------------------"

    return os.path.join(traceid_dir, 'files')

#%%
# =============================================================================
# Create time courses for ROIs:
# =============================================================================

def get_roi_timecourses(TID, RID, si_info, input_filedir='/tmp', rootdir='', create_new=False):
    '''
    Concatenate extracted traces from each file into one set of traces. At this level,
    organization is by ROI, not by .tif file.
    '''

    session_dir = RID['DST'].split('/ROIs')[0]
    info = get_info_from_tiff_dir(TID['SRC'], session_dir)
    print "Got trace info:"
    pp.pprint(info)

    traceid_dir = TID['DST']
    if rootdir not in traceid_dir:
        traceid_dir = replace_root(traceid_dir, rootdir, info['animalid'], info['session'])
    traceid_dir = TID['DST']
    if rootdir not in traceid_dir:
        traceid_dir = replace_root(traceid_dir, rootdir, info['animalid'], info['session'])

    print "-----------------------------------------------------------------------"
    print "TID %s -- sorting traces by ROI..." % TID['trace_hash']
    t_roi = time.time()

    #% Load raw traces:
    try:
        filetrace_fns = [f for f in os.listdir(os.path.join(traceid_dir, 'files')) if f.endswith('hdf5') and 'rawtraces' in f]
        print "Found traces by file for %i tifs in dir: %s" % (len(filetrace_fns), os.path.join(traceid_dir, 'files'))
    except Exception as e:
        print "Unable to find extracted tracestructs from trace set: %s" % TID['trace_id']
        print "Aborting with error:"
        traceback.print_exc()

    # Create output file for parsed traces:
    # -----------------------------------------------------------------------------
    # Check if time courses file already exists:
    existing_tcourse_fns = sorted([t for t in os.listdir(traceid_dir) if 'roi_timecourses' in t and t.endswith('hdf5')], key=natural_keys)
    if len(existing_tcourse_fns) > 0 and create_new is False:
        roi_tcourse_filepath = os.path.join(traceid_dir, existing_tcourse_fns[-1])
        print "Loaded existing ROI time courses file: %s" % roi_tcourse_filepath
    else:
        tstamp = datetime.datetime.now().strftime("%Y%m%d_%H_%M_%S")
        roi_tcourse_fn = 'roi_timecourses_%s.hdf5' % tstamp
        roi_tcourse_filepath = os.path.join(traceid_dir, roi_tcourse_fn)

        roi_outfile = h5py.File(roi_tcourse_filepath, 'w')
        roi_outfile.attrs['tiff_source'] = TID['SRC']
        roi_outfile.attrs['trace_id'] = TID['trace_id']
        roi_outfile.attrs['trace_hash'] = TID['trace_hash']
        roi_outfile.attrs['trace_source'] = traceid_dir
        roi_outfile.attrs['roiset_id'] = RID['roi_id']
        roi_outfile.attrs['roiset_hash'] = RID['rid_hash']
        roi_outfile.attrs['run'] = info['run']
        roi_outfile.attrs['session'] = info['session']
        roi_outfile.attrs['acquisition'] = info['acquisition']
        roi_outfile.attrs['animalid'] = info['animalid']
        roi_outfile.attrs['creation_time'] = tstamp #datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Concatenate time courses across all files to create single time-source for RUN:
        # -----------------------------------------------------------------------------
        tmp_tracestruct = h5py.File(os.path.join(traceid_dir, 'files', filetrace_fns[0]), 'r')
        ntiffs = si_info['ntiffs']
        dims = tmp_tracestruct.attrs['dims']
        total_nframes_in_run = tmp_tracestruct.attrs['dims'][-1] * ntiffs #tmp_tracestruct['Slice01']['rawtraces'].shape[0] * ntiffs
        tmp_tracestruct.close(); del tmp_tracestruct

        nframes_in_file = si_info['nframes_per_file'] #uninfo['nvolumes']
        curr_frame_idx = 0
        tiff_start_fridxs = []
        for fi in range(ntiffs):
            tiff_start_fridxs.append(fi * nframes_in_file)

        try:
            for filetrace_fn in sorted(filetrace_fns, key=natural_keys):
                fidx_in_run = int(filetrace_fn[4:7]) - 1 # Get IDX of tiff file in run (doesn't assume all tiffs continuous)
                curr_frame_idx = tiff_start_fridxs[fidx_in_run]
                print "Loading file:", filetrace_fn
                filetrace = h5py.File(os.path.join(traceid_dir, 'files', filetrace_fn), 'r')         # keys are SLICES (Slice01, Slice02, ...)

                roi_counter = 0
                for currslice in sorted(filetrace.keys(), key=natural_keys):
                    print "Loading slice:", currslice
                    maskarray = filetrace[currslice]['masks']
                    d1, d2 = dims[0:2] #tracefile[currslice]['traces']'rawtraces'].attrs['dims'][0:-1]
                    T = dims[-1] #tracefile[currslice]['rawtraces'].attrs['nframes']
                    src_roi_idxs = filetrace[currslice]['masks'].attrs['src_roi_idxs']
                    nr = filetrace[currslice]['masks'].attrs['nr'] #maskarray.shape[1]
                    nb = filetrace[currslice]['masks'].attrs['nb']
                    ncomps = nr + nb
                    masks = np.reshape(maskarray, (d1, d2, nr+nb), order='C')

                    bgidx = 0
                    for ridx in range(ncomps): #, roi in enumerate(src_roi_idxs):
                        if (nb > 0) and (ridx >= nr):
                            bgidx += 1
                            is_background = True
                            roiname = 'bg%02d' % bgidx
                        else:
                            is_background = False
                            roi_counter += 1
                            roiname = 'roi%05d' % int(roi_counter)

                        # Create unique ROI group:
                        if roiname not in roi_outfile.keys():
                            roi_grp = roi_outfile.create_group(roiname)
                            roi_grp.attrs['slice'] = currslice
                            roi_grp.attrs['roi_img_path'] = filetrace[currslice]['zproj'].attrs['img_source']
                        else:
                            roi_grp = roi_outfile[roiname]

                        if 'mask' not in roi_grp.keys():
                            roi_mask = roi_grp.create_dataset('mask', masks[:,:,ridx].shape, masks[:,:,ridx].dtype)
                            roi_mask[...] = masks[:,:,ridx]
                            roi_grp.attrs['id_in_set'] = roi_counter #roi
                            roi_grp.attrs['id_in_src'] = src_roi_idxs[ridx] #ridx
                            roi_grp.attrs['idx_in_slice'] = ridx
                            roi_mask.attrs['slice'] = currslice
                            roi_mask.attrs['is_background'] = is_background

                        # Add time courses:
                        trace_types = filetrace[currslice]['traces'].keys()
                        if 'timecourse' not in roi_grp.keys():
                            tcourse_grp = roi_grp.create_group('timecourse')
                        else:
                            tcourse_grp = roi_grp['timecourse']

                        for trace_type in trace_types:
                            curr_tcourse = filetrace[currslice]['traces'][trace_type][:, ridx]
                            if trace_type not in tcourse_grp.keys():
                                roi_tcourse = tcourse_grp.create_dataset(trace_type, (total_nframes_in_run,), curr_tcourse.dtype)
                            else:
                                roi_tcourse = tcourse_grp[trace_type]
                            roi_tcourse[curr_frame_idx:curr_frame_idx+nframes_in_file] = curr_tcourse
                            roi_tcourse.attrs['source_file'] = os.path.join(traceid_dir, 'files', filetrace_fn)

                        print "%s: added frames %i:%i, from %s." % (roiname, curr_frame_idx, curr_frame_idx+nframes_in_file, filetrace_fn)
        except Exception as e:
            print "--- TID %s: ERROR extracting traces from file %s..." % (TID['trace_hash'], filetrace_fn)
            traceback.print_exc()
        finally:
            roi_outfile.close()

        ## Rename FRAME file with hash:
        roi_tcourse_filehash = hash_file(roi_tcourse_filepath)

        # Check if existing files:
        outdir = os.path.split(roi_tcourse_filepath)[0]
        existing_files = [f for f in os.listdir(outdir) if 'roi_timecourses_' in f and f.endswith('hdf5') and roi_tcourse_filehash not in f and tstamp not in f]
        if len(existing_files) > 0:
            old = os.path.join(outdir, 'old')
            if not os.path.exists(old):
                os.makedirs(old)
            for f in existing_files:
                shutil.move(os.path.join(outdir, f), os.path.join(old, f))

        roi_tcourse_filepath = hash_file_read_only(roi_tcourse_filepath)

        print "TID %s -- Finished extracting time course for run %s by roi." % (TID['trace_hash'], info['run'])
        print_elapsed_time(t_roi)
        print "Saved ROI TIME COURSE file to:", roi_tcourse_filepath

    return roi_tcourse_filepath


#%%

def extract_options(options):
    parser = optparse.OptionParser()

    # PATH opts:
    parser.add_option('-D', '--root', action='store', dest='rootdir', default='/nas/volume1/2photon/data', help='data root dir (root project dir containing all animalids) [default: /nas/volume1/2photon/data, /n/coxfs01/2pdata if --slurm]')
    parser.add_option('-i', '--animalid', action='store', dest='animalid', default='', help='Animal ID')
    parser.add_option('-S', '--session', action='store', dest='session', default='', help='session dir (format: YYYMMDD_ANIMALID')
    parser.add_option('-A', '--acq', action='store', dest='acquisition', default='FOV1', help="acquisition folder (ex: 'FOV1_zoom3x') [default: FOV1]")
    parser.add_option('-R', '--run', action='store', dest='run', default='', help="name of run dir containing tiffs to be processed (ex: gratings_phasemod_run1)")
    parser.add_option('--default', action='store_true', dest='default', default='store_false', help="Use all DEFAULT params, for params not specified by user (no interactive)")
    parser.add_option('--slurm', action='store_true', dest='slurm', default=False, help="set if running as SLURM job on Odyssey")
    parser.add_option('-t', '--trace-id', action='store', dest='trace_id', default='', help="Trace ID for current trace set (created with set_trace_params.py, e.g., traces001, traces020, etc.)")

    parser.add_option('--new', action="store_true",
                      dest="create_new", default=False, help="Set flag to create new output files (/paradigm/parsed_frames.hdf5, roi_trials.hdf5")

    # Pupil filtering info:
    parser.add_option('--no-pupil', action="store_false",
                      dest="filter_pupil", default=True, help="Set flag NOT to filter PSTH traces by pupil threshold params")
    parser.add_option('-r', '--rad', action="store",
                      dest="pupil_size_thr", default=25, help="Cut-off for pupil radius, if --pupil set [default: 30]")
    parser.add_option('-d', '--dist', action="store",
                      dest="pupil_dist_thr", default=15, help="Cut-off for pupil distance from start, if --pupil set [default: 5]")
    parser.add_option('-x', '--blinks', action="store",
                      dest="pupil_max_nblinks", default=1, help="Cut-off for N blinks allowed in trial, if --pupil set [default: 1 (i.e., 0 blinks allowed)]")

    (options, args) = parser.parse_args(options)

    return options

#%%
def extract_traces(options):
    # Set USER INPUT options:
    options = extract_options(options)

    rootdir = options.rootdir
    animalid = options.animalid
    session = options.session
    acquisition = options.acquisition
    run = options.run
    trace_id = options.trace_id
    slurm = options.slurm
    if slurm is True:
        if 'coxfs01' not in rootdir:
            rootdir = '/n/coxfs01/2p-data'



    create_new = options.create_new
    auto = options.default

    #%
    # NOTE:  caiman2D ROIs are already "normalized" or weighted (see format_rois_nmf in get_rois.py).
    # These masks can be directly applied to tiff movies, or can be applied to temporal component mat from NMF results (.npz)
    normalize_roi_types = ['manual2D_circle', 'manual2D_polygon', 'manual2D_square', 'manual2D_warp', 'opencv_blob_detector']

    print "======================================================================="
    print "Trace Set: %s -- Starting trace extraction..." % trace_id
    t_start = time.time()


    #% Get meta info for run:
    # =============================================================================
    run_dir = os.path.join(rootdir, animalid, session, acquisition, run)

    run_dir = os.path.join(rootdir, animalid, session, acquisition, run)
    si_info = get_frame_info(run_dir)


    # Load specified trace-ID parameter set:
    # =============================================================================
    trace_dir = os.path.join(run_dir, 'traces')
    tmp_tid_dir = os.path.join(trace_dir, 'tmp_tids')

    if not os.path.exists(trace_dir):
        os.makedirs(trace_dir)
    print "RUN DIR:", run_dir
    TID = load_TID(run_dir, trace_id, auto=auto)

    #%
    # Get source tiff paths using trace-ID params:
    # =============================================================================
    trace_hash = TID['trace_hash']

    tiff_dir = TID['SRC']
    roi_name = TID['PARAMS']['roi_id']
    if rootdir not in tiff_dir:
        tiff_dir = replace_root(tiff_dir, rootdir, animalid, session)

    tiff_files = sorted([t for t in os.listdir(tiff_dir) if t.endswith('tif')], key=natural_keys)
    print "Found %i tiffs in dir %s.\nExtracting traces with ROI set %s." % (len(tiff_files), tiff_dir, roi_name)

    #%
    # Create output dirs and files:
    # =============================================================================

    traceid_dir = os.path.join(trace_dir, '%s_%s' % (TID['trace_id'], TID['trace_hash']))
    filetrace_dir = os.path.join(traceid_dir, 'files')
    if not os.path.exists(filetrace_dir):
        os.makedirs(filetrace_dir)

    trace_figdir = os.path.join(traceid_dir, 'figures')
    if not os.path.exists(trace_figdir):
        os.makedirs(trace_figdir)

    #%
    # Create mask array and save mask images for each slice specified in ROI set:
    # =============================================================================
    # Load ROI set specified in Traces param set:
    roi_dir = os.path.join(rootdir, animalid, session, 'ROIs')
    roidict_path = os.path.join(roi_dir, 'rids_%s.json' % session)
    with open(roidict_path, 'r') as f:
        roidict = json.load(f)
    RID = roidict[TID['PARAMS']['roi_id']]

    #% For each specified SLICE in this ROI set, create 2D mask array:
    # TODO:  Need to make MATLAB (manual methods) HDF5 output structure the same
    # as python-based methods... if-checks hacked for now...

    # Load mask file:
    if rootdir not in RID['DST']:
        rid_dst = replace_root(RID['DST'], rootdir, animalid, session)
        notnative = True
    else:
        rid_dst = RID['DST']
        notnative = False

    mask_path = os.path.join(rid_dst, 'masks.hdf5')

    print "-----------------------------------------------------------------------"
    print "TID %s -- Getting mask info..." % trace_hash
    t_mask = time.time()

    # Check if ROI masks need to be normalized before applying to traces (non-NMF methods):
    normalize_rois = False
    if RID['roi_type'] == 'coregister' and RID['PARAMS']['options']['source']['roi_type'] in normalize_roi_types:
        normalize_rois = True
    elif RID['roi_type'] in normalize_roi_types:
        normalize_rois = True
    maskinfo = get_mask_info(mask_path, ntiffs=len(tiff_files))

    # Check if formatted MASKS dict exists and load, otherwise, create new:
    maskdict_path = os.path.join(traceid_dir, 'MASKS.pkl')
    if create_new is True or not os.path.exists(maskdict_path):
        MASKS = get_masks(maskinfo, RID, normalize_rois=normalize_rois, notnative=notnative, rootdir=rootdir, animalid=animalid, session=session)
        with open(maskdict_path, 'wb') as f:
            pkl.dump(MASKS, f, protocol=pkl.HIGHEST_PROTOCOL)
        del MASKS

    # Check if alrady have plotted masks, if not, create new:
    all_files = ['File%03d' % int(i+1) for i in range(len(tiff_files))]
    tiffs_in_set = [t for t in all_files if t not in TID['PARAMS']['excluded_tiffs']]
    mask_figdir = os.path.join(trace_figdir, 'masks')
    if not os.path.exists(mask_figdir):
        os.makedirs(mask_figdir)
    maskfigs = [i for i in os.listdir(mask_figdir) if 'rois_File' in i and i.endswith('png')]
    if len(maskfigs) == 0 or create_new is True:
        plot_roi_masks(TID, RID, mask_figdir=mask_figdir, rootdir=rootdir)

    print "TID %s - Got mask info from ROI set %s." % (trace_hash, RID['roi_id'])
    print_elapsed_time(t_mask)
    print "-----------------------------------------------------------------------"

    #%
    # Apply masks to .tif files:
    # -------------------------
    if create_new is True or not len(os.listdir(filetrace_dir)) == len(maskfigs):
        filetrace_dir = apply_masks_to_movies(TID, RID, si_info, output_filedir=filetrace_dir, rootdir=rootdir)

    #%
    # Organize timecourses by stim-type for each ROI:
    # -----------------------------------------------
    roi_tcourse_filepath = get_roi_timecourses(TID, RID, si_info, input_filedir=filetrace_dir, rootdir=rootdir, create_new=create_new)

    print "-----------------------------------------------------------------------"

    #% move tmp file and clean up:
    tmp_tid_fn = 'tmp_tid_%s.json' % trace_hash
    completed_tid_dir = os.path.join(tmp_tid_dir, 'completed')
    if not os.path.exists(completed_tid_dir):
        os.makedirs(completed_tid_dir)
    if os.path.exists(os.path.join(tmp_tid_dir, tmp_tid_fn)):
        os.rename(os.path.join(tmp_tid_dir, tmp_tid_fn), os.path.join(completed_tid_dir, tmp_tid_fn))
    print "Cleaned up tmp tid files."

    #%
    print "*** TID %s *** COMPLETED TRACE EXTRACTION!" % trace_hash
    #print_elapsed_time(t_start)
    print "======================================================================="

#%% GET PLOTS:
def main(options):
    #options = extract_options(options)
    extract_traces(options)

    print "*** Creating ROI dataframes ***"
    roidata_filepath, roi_psth_dir = acq.create_roi_dataframes(options)


if __name__ == '__main__':
    main(sys.argv[1:])

