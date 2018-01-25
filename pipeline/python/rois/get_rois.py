#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Select from a set of methods for ROI extraction.
Currently supports:
    - manual2D_circle
    - manual2D_square
    - manual2D_polygon
    - caiman2D
    - blob_detector

User-provided option with specified ROI ID (e.g., 'rois002') OR roi_type.
If <roi_type> is provided, RID set is created with set_roid_params.py.
ROI ID will always take precedent.

INPUTS:
    rootdir
    animalid
    session
    (roi_id)
    (roi params)
    
OUTPUTS:
    <path/to/roi/id>/masks.hdf5
        masks :  hdf5 file with a group for each file source from which ROIs are extracted
            masks['File001']['com'] = hdf5 dataset of array of coords for each roi's center-of-mass
            masks['File001']['masks'] = hdf5 dataset of array containg masks, size is d1xd2(xd3?) x nrois
            masks['File001'].attrs['source_file'] :  
        
        masks has attributes:
            masks.attrs['roi_id']             :  name identifier for ROI ID set
            masks.attrs['rid_hash']           :  hash identifier for ROI ID set
            masks.attrs['keep_good_rois']     :  whether to keep subset of ROIs that pass some "roi evalation" threshold (currently, only for caiman2D)
            masks.attrs['ntiffs_in_set']      :  number of tiffs included in current ROI set (excludes bad files)
            masks.attrs['mcmetrics_filepath'] :  full path to mc_metrics.hdf5 file (if motion-corrected tiff source is used for ROI extraction)
            masks.attrs['mcmetric_type']      :  metric used to determine bad files (i.e., 'excluded_tiffs')
            masks.attrs['creation_date']      :  date string created, format 'YYYY-MM-DD hh:mm:ss'
    
    <path/to/roi/id>/roiparams.json
        - info about extracted roi set
        - evaluation params
        - excluded tiffs
        - whether ROIs were filtered by some metric
        - coregisteration parms, if applicable


Created on Thu Jan  4 11:54:38 2018
@author: julianarhee
"""
import matplotlib
matplotlib.use('Agg')
import os
import h5py
import json
import datetime
import optparse
import pprint
import time
import traceback
import scipy
import pylab as pl
import numpy as np
from pipeline.python.utils import natural_keys, write_dict_to_json, load_sparse_mat, save_sparse_hdf5, print_elapsed_time
from pipeline.python.rois import extract_rois_caiman as rcm
from pipeline.python.rois import coregister_rois as reg
from pipeline.python.set_roi_params import post_rid_cleanup
from pipeline.python.rois.utils import load_RID, get_source_paths

from scipy.sparse import spdiags
from caiman.utils.visualization import get_contours
from past.utils import old_div

def timer(start,end):
    hours, rem = divmod(end-start, 3600)
    minutes, seconds = divmod(rem, 60)
    formatted_time = "{:0>2}:{:0>2}:{:05.2f}".format(int(hours),int(minutes),seconds)
    return formatted_time
   
pp = pprint.PrettyPrinter(indent=4)

#%%
def format_rois_nmf(nmf_filepath, roiparams, zproj_type='mean', pass_rois=None, coreg_rois=None):
    """
    Get shaped masks (filtered, if specified) and coordinate list for ROIs.
    Also return original indices of final ROIs (0-indexed).
    """
    nmf = np.load(nmf_filepath)

    d1 = int(nmf['dims'][0])
    d2 = int(nmf['dims'][1])
    if len(nmf['dims']) > 2:
        is_3D = True
        d3 = int(nmf['dims'][2])
        dims = (d1, d2)
    else:
        is_3D = False
        dims = (d1, d2)
        
    # Get zprojected image:
    if zproj_type == 'corr':
        img = nmf['Cn']
    else:
        img = nmf['Av']

    A = nmf['A'].all().tocsc()
    b = nmf['b']
    C = nmf['C']
    f = nmf['f']
#    A2 = A.copy()
#    A2.data **= 2
#    nA2 = np.sqrt(np.array(A2.sum(axis=0))).squeeze()
#    rA = A * spdiags(old_div(1, nA2), 0, nr, nr)
#    rA = rA.todense()
#    nr = A.shape[1]

    nr = np.shape(A)[-1]
    nb = b.shape[1]
    
    # Keep background as components:
    Ab = scipy.sparse.hstack((A, b)).tocsc()
    Cf = np.vstack((C, f))

    A2 = Ab.copy()
    A2.data **= 2.
    nA2 = np.sqrt(np.array(A2.sum(axis=0))).squeeze()
    
    # normalize by each pixel's contribution to spatial component:
    rA = Ab * spdiags(old_div(1., nA2), 0., nr+nb, nr+nb)
    AB = rA.todense()
    
    # Get center of mass for each ROI:
    coors = get_contours(A, dims, thr=0.9)
    roi_idxs = np.arange(0, nr)

    # Create masks:
    if is_3D:
        masks = np.reshape(np.array(AB), (d1, d2, d3, nr+nb), order='F')
    else:
        masks = np.reshape(np.array(AB), (d1, d2, nr+nb), order='F')
        
    # Filter coors and masks:
    if roiparams['keep_good_rois'] is True:
        if pass_rois is None:
            pass_rois = nmf['idx_components']    # Get idxs of ROIs that "pass" evaluation
        roi_idxs = roi_idxs[pass_rois]           # Update ROI index list
        
    if coreg_rois is not None:                   # coreg_rois = indices into either "pass" rois (if keep_good_rois==True) or just the org src 
        roi_idxs = roi_idxs[coreg_rois]   

    roi_idxs = np.append(roi_idxs, nr)          # Append the "background component" to the ROI list:
    
    # Only return selected masks and coord info:
    if is_3D:
        masks = masks[:, :, :, roi_idxs]
    else:
        masks = masks[:, :, roi_idxs]
    coors = [coors[i] for i in roi_idxs if not i==nr]
    rA = rA[:, roi_idxs]
    Cf = Cf[roi_idxs, :]
    
    #cc1 = [[l[0] for l in n['coordinates']] for n in coors]
    #cc2 = [[l[1] for l in n['coordinates']] for n in coors]
    #coords = [[(x,y) for x,y in zip(cc1[n], cc2[n])] for n in range(len(cc1))]
    #coms = np.array([np.array(n) for n in coords])
    
    return masks,img, coors, roi_idxs, is_3D, nb, rA, Cf

#%

#%%

parser = optparse.OptionParser()

# PATH opts:
parser.add_option('-R', '--root', action='store', dest='rootdir', default='/nas/volume1/2photon/data', help='data root dir (root project dir containing all animalids) [default: /nas/volume1/2photon/data, /n/coxfs01/2pdata if --slurm]')
parser.add_option('-i', '--animalid', action='store', dest='animalid', default='', help='Animal ID')
parser.add_option('-S', '--session', action='store', dest='session', default='', help='session dir (format: YYYMMDD_ANIMALID')

parser.add_option('--default', action='store_true', dest='default', default=False, help="Use all DEFAULT params, for params not specified by user (no interactive)")
parser.add_option('--slurm', action='store_true', dest='slurm', default=False, help="set if running as SLURM job on Odyssey")
parser.add_option('-r', '--roi-id', action='store', dest='roi_id', default='', help="ROI ID for rid param set to use (created with set_roi_params.py, e.g., rois001, rois005, etc.)")

parser.add_option('-z', '--zproj', action='store', dest='zproj_type', default="mean", help="zproj to use for display [default: mean]")

# Eval opts:
parser.add_option('--good', action="store_true",
                  dest="keep_good_rois", default=False, help="Set flag to only keep good components (useful for avoiding computing massive ROI sets)")
parser.add_option('--max', action="store_true",
                  dest="use_max_nrois", default=False, help="Set flag to use file with max N components (instead of reference file) [default uses reference]")
    
# Coregistration options:
parser.add_option('-t', '--maxthr', action='store', dest='dist_maxthr', default=0.1, help="[coreg]: threshold for turning spatial components into binary masks [default: 0.1]")
parser.add_option('-n', '--power', action='store', dest='dist_exp', default=0.1, help="[coreg]: power n for distance between masked components: dist = 1 - (and(M1,M2)/or(M1,M2)**n [default: 1]")
parser.add_option('-d', '--dist', action='store', dest='dist_thr', default=0.5, help="[coreg]: threshold for setting a distance to infinity, i.e., illegal matches [default: 0.5]")
parser.add_option('-o', '--overlap', action='store', dest='dist_overlap_thr', default=0.8, help="[coreg]: overlap threshold for detecting if one ROI is subset of another [default: 0.8]")

parser.add_option('-E', '--eval', action="store",
                  dest="eval_key", default=None, help="Evaluation key from ROI source <rid_dir>/evaluation")
parser.add_option('-M', '--mcmetric', action="store",
                  dest="mcmetric", default='zproj_corrcoefs', help="Motion-correction metric to use for identifying tiffs to exclude [default: zproj_corrcoefs]")

(options, args) = parser.parse_args()

# Set USER INPUT options:
rootdir = options.rootdir
animalid = options.animalid
session = options.session
roi_id = options.roi_id
slurm = options.slurm
auto = options.default

if slurm is True:
    if 'coxfs01' not in rootdir:
        rootdir = '/n/coxfs01/2p-data'

keep_good_rois = options.keep_good_rois
use_max_nrois = options.use_max_nrois

dist_maxthr = options.dist_maxthr
dist_exp = options.dist_exp
dist_thr = options.dist_thr
dist_overlap_thr = options.dist_overlap_thr

zproj_type= options.zproj_type

eval_key = options.eval_key
mcmetric = options.mcmetric

#%%
#rootdir = '/nas/volume1/2photon/data'
#animalid = 'JR063' #'JR063'
#session = '20171128_JR063' #'20171128_JR063'
#roi_id = 'rois002'
#slurm = False
#auto = False
##
#keep_good_rois = True       # Only keep "good" ROIs from a given set (TODO:  add eval for ROIs -- right now, only have eval for NMF and coregister)
##
### COREG-SPECIFIC opts:
#use_max_nrois = True        # Use file which has the max N ROIs as reference (alternative is to use reference file)
#dist_maxthr = 0.1
#dist_exp = 0.1
#dist_thr = 0.5
#dist_overlap_thr = 0.8
##
#eval_key = '2018_01_22_18_50_59'
#mcmetric = 'zproj_corrcoefs'
#zproj_type = 'mean'

#min_SNR_low = 1.5
#min_rval_low = 0.6
#evaluate_rois=True


#%%
session_dir = os.path.join(rootdir, animalid, session)

# =============================================================================
# Load specified ROI-ID parameter set:
# =============================================================================
try:
    RID = load_RID(session_dir, roi_id, auto=auto)
    print "Evaluating ROIs from set: %s" % RID['roi_id']
except Exception as e:
    print "-- ERROR: unable to open source ROI dict. ---------------------"
    traceback.print_exc()
    print "---------------------------------------------------------------"
    

#%%
# =============================================================================
# Get meta info for current run and source tiffs using trace-ID params:
# =============================================================================
tiff_sourcedir = RID['SRC']
path_parts = tiff_sourcedir.split(session_dir)[-1].split('/')
acquisition = path_parts[1]
run = path_parts[2]
process_dirname = path_parts[4]
process_id = process_dirname.split('_')[0]

roi_source_paths, tiff_source_paths, filenames, mc_excluded_tiffs, mcmetrics_filepath = get_source_paths(session_dir, RID, check_motion=True, 
                                                                                                         mcmetric=mcmetric, 
                                                                                                         acquisition=acquisition,
                                                                                                         run=run,
                                                                                                         process_id=process_id)

#%%
# =============================================================================
# Extract ROIs using specified method:
# =============================================================================
print "Extracting ROIs...====================================================="
roi_type = RID['roi_type']
rid_hash = RID['rid_hash']

format_roi_output = False
src_roi_type = None
t_start = time.time()
if len(mc_excluded_tiffs) > 0:
    exclude_str = ','.join([int(fn[4:]) for fn in mc_excluded_tiffs])
    
if roi_type == 'caiman2D':
    #%
    roi_opts = ['-R', rootdir, '-i', animalid, '-S', session, '-A', acquisition, '-r', run, '-p', rid_hash]
    if slurm is True:
        roi_opts.extend(['--slurm'])
    if len(exclude_str) > 0:
        roi_opts.extend(['-x', exclude_str])
        
    nmf_hash, rid_hash = rcm.extract_cnmf_rois(roi_opts)
    
    # Clean up tmp RID files:
    session_dir = os.path.join(rootdir, animalid, session)
    post_rid_cleanup(session_dir, rid_hash)
    
    format_roi_output = True
    #%
    
elif roi_type == 'blob_detector':
    #% Do some other stuff
    print "blobs"
    format_roi_output = False

elif 'manual' in roi_type:
    # Do some matlab-loading stuff ?
    print "manual"
    format_roi_output = False

elif roi_type == 'coregister':
    #%
    src_roi_id = RID['PARAMS']['options']['source']['roi_id']
    src_roi_dir = RID['PARAMS']['options']['source']['roi_dir']
    
    #% Set COREG opts:
    coreg_opts = ['-R', rootdir, '-i', animalid, '-S', session, '-r', roi_id,
                  '-t', dist_maxthr,
                  '-n', dist_exp,
                  '-d', dist_thr,
                  '-o', dist_overlap_thr]
    
    if use_max_nrois is True: # == 'max':
        coreg_opts.extend(['--max'])
    if keep_good_rois is True:
        coreg_opts.extend(['--good'])
    
    #% RUN COREGISTRATION
    print "==========================================================="
    print "RID %s -- Running coregistration..." % rid_hash
    print "RID %s -- Source ROI set is: %s" % (rid_hash, src_roi_id)
    if eval_key is None and keep_good_rois is False:
        # Just run coregistration on default (if nmf rois, will use source eval-params if "keep_good_rois" is True)
        ref_rois, params_thr, coreg_outpath = reg.run_coregistration(coreg_opts)
        src_eval_filepath = None
    else:
        # Load ROI info for "good" rois to include:
        try:
            print "-----------------------------------------------------------"
            print "Loading evaluation results for src roi set"
            # Load eval info:
            src_eval_filepath = os.path.join(src_roi_dir, 'evaluation', 'evaluation_%s' % eval_key, 'evaluation_results_%s.hdf5' % eval_key)
            assert os.path.exists(src_eval_filepath), "Specfied EVAL src file does not exist!\n%s" % src_eval_filepath
            src_eval = h5py.File(src_eval_filepath, 'r')
        except Exception as e:
            print "Error loading specified eval file:\n%s" % src_eval_filepath
            traceback.print_exc()
            print "-----------------------------------------------------------"
            try:
                evaldict_filepath = os.path.join(src_roi_dir, 'evaluation', 'evaluation_info.json')
                with open(evaldict_filepath, 'r') as f:
                    evaldict = json.load(f)
                eval_list = sorted(evaldict.keys(), key=natural_keys)
                print "Found evaluation keys:"
                if auto is False:
                    while True:
                        if len(eval_list) > 1:
                            for eidx, ekey in enumerate(eval_list):
                                print eidx, ekey
                                eval_select_idx = input('Select IDX of evaluation key to view: ')
                        else:
                            eval_select_idx = 0
                            print "Only 1 evaluation set found: %s" % eval_list[eval_select_idx]
                        pp.pprint(evaldict[eval_list[eval_select_idx]])
                        confirm_eval = raw_input('Enter <Y> to use this eval set, or <n> to return: ')
                        if confirm_eval == 'Y':
                            eval_key = eval_list[eval_select_idx].split('evaluation_')[-1]
                            print "Using key: %s" % eval_key
                            break
                else:
                    print "Auto is ON, using most recent evaluation set: %s" % eval_key
                    eval_key = eval_list[-1].split('evaluation_')[-1]
                    pp.pprint(evaldict[eval_list[-1]])
                
                src_eval_filepath = os.path.join(src_roi_dir, 'evaluation', 'evaluation_%s' % eval_key, 'evaluation_results_%s.hdf5' % eval_key)
                src_eval = h5py.File(src_eval_filepath, 'r')
            except Exception as e:
                print "RID %s -- ERROR: Can't load source evaluation file..." % rid_hash
                traceback.print_exc()
                print "Aborting..."
                print "-----------------------------------------------------------"
        #%
        coreg_opts.extend(['--roipath=%s' % src_eval_filepath])
        
        #%
        ref_rois, params_thr, coreg_results_path = reg.run_coregistration(coreg_opts)

    print("Found %i common ROIs matching reference." % len(ref_rois))

    format_roi_output = True
    src_roi_type = RID['PARAMS']['options']['source']['roi_type']
    
    #%
else:
    print "ERROR: %s -- roi type not known..." % roi_type

print "RID %s -- Finished ROI extration!" % rid_hash
print_elapsed_time(t_start)
print "======================================================================="


#%% Save ROI params info:
    
# TODO: Include ROI eval info for other methods?
# TODO: If using NMF eval methods, make func to do evaluation at post-extraction step (since extract_rois_caiman.py keeps all when saving anyway)
roiparams = dict()
rid_dir = RID['DST']

if roi_type == 'caiman2D':
    roiparams['eval'] = RID['PARAMS']['options']['eval']
elif roi_type == 'coregister':
    roiparams['eval'] = params_thr['eval']
    
roiparams['keep_good_rois'] = keep_good_rois
roiparams['excluded_tiffs'] = mc_excluded_tiffs
roiparams['roi_type'] = roi_type
roiparams['roi_id'] = roi_id
roiparams['rid_hash'] = rid_hash

roiparams_filepath = os.path.join(rid_dir, 'roiparams.json') # % (str(roi_id), str(rid_hash)))
with open(roiparams_filepath, 'w') as f:
    write_dict_to_json(roiparams, roiparams_filepath)
    
    
#%%
# =============================================================================
# Format ROI output to standard, if applicable:
# =============================================================================

if format_roi_output is True :
    rid_figdir = os.path.join(rid_dir, 'figures')
    if not os.path.exists(rid_figdir):
        os.makedirs(rid_figdir)
    
    mask_filepath = os.path.join(rid_dir, 'masks.hdf5')
    maskfile = h5py.File(mask_filepath, 'w')
    maskfile.attrs['roi_type'] = roi_type
    maskfile.attrs['roi_id'] = roi_id
    maskfile.attrs['rid_hash'] = rid_hash
    maskfile.attrs['animal'] = animalid
    maskfile.attrs['session'] = session
    maskfile.attrs['ref_file'] = params_thr['ref_filename']
    maskfile.attrs['creation_date'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    maskfile.attrs['keep_good_rois'] = keep_good_rois
    maskfile.attrs['ntiffs_in_set'] = len(filenames)
    maskfile.attrs['mcmetrics_filepath'] = mcmetrics_filepath
    maskfile.attrs['mcmetric_type'] = mcmetric
    maskfile.attrs['zproj'] = zproj_type
    
    try:
        if roi_type == 'caiman2D' or (roi_type == 'coregister' and src_roi_type == 'caiman2D'):

            for fidx, nmfpath in enumerate(sorted(roi_source_paths, key=natural_keys)):
                
                curr_file = filenames[fidx]
                print "Creating ROI masks for %s" % curr_file
                
                # Create group for current file:
                filegrp = maskfile.create_group(filenames[fidx])
                filegrp.attrs['source_file'] = nmfpath

                # Format NMF output to standard masks:
                print "Formatting masks..."
                if roi_type == 'coregister':
                    # Load coreg results:
                    coreg_byfile = h5py.File(coreg_results_path, 'r')
                    
                    # Get masks:
                    masks, img, coord_info, roi_idxs, is_3D, nb, Ab, Cf = format_rois_nmf(nmfpath, roiparams, 
                                                                         pass_rois=coreg_byfile[curr_file]['roi_idxs'], 
                                                                         coreg_rois=coreg_byfile[curr_file]['universal_matches'])
                else:
                    masks, img, coord_info, roi_idxs, is_3D, nb, Ab, Cf = format_rois_nmf(nmfpath, roiparams, zproj_type=zproj_type)
                maskfile.attrs['is_3D'] = is_3D
                
                roi_names = ["roi%04d" % int(ridx+1) for ridx in range(len(roi_idxs) - nb)]
                
                # Save masks for current file (TODO: separate slices?)
                print('Mask array:', masks.shape)
                currmasks = filegrp.create_dataset('masks', masks.shape, masks.dtype)
                currmasks[...] = masks
                currmasks.attrs['src_roi_idxs'] = roi_idxs
                currmasks.attrs['nrois'] = len(roi_idxs) - nb
                currmasks.attrs['background'] = nb
                
                # Save spatial and temporal comps:
                save_sparse_hdf5(Ab, '%s/Ab' % curr_file, mask_filepath)
                save_sparse_hdf5(scipy.sparse.csc_matrix(Cf, dtype=Cf.dtype), '%s/Cf' % curr_file, mask_filepath)

                # Save CoM for each ROI:
                coms = np.array([r['CoM'] for r in coord_info])
                currcoms = filegrp.create_dataset('coms', coms.shape, coms.dtype)
                currcoms[...] = coms
                
                # Save coords for each ROI:
                for ridx, roi in enumerate(coord_info):
                    curr_roi = filegrp.create_dataset('/'.join(['coords', roi_names[ridx]]), roi['coordinates'].shape, roi['coordinates'].dtype)
                    curr_roi[...] = roi['coordinates']
                    curr_roi.attrs['roi_source'] = nmfpath
                    curr_roi.attrs['id_in_set'] = roi_names[ridx]
                    curr_roi.attrs['id_in_src'] = roi['neuron_id']
                    curr_roi.attrs['idx_in_src'] = roi_idxs[ridx]
                    if roi_type == 'coregister':
                        curr_roi.attrs['idx_in_coreg'] = coreg_byfile[curr_file]['universal_matches']
                
                # Save zproj image:
                zproj = filegrp.create_dataset('zproj_img', img.shape, img.dtype)
                zproj[...] = img
                zproj.attrs['zproj_type'] = zproj_type

                # Plot figure with ROI masks: (1-indexed for naming)
                print "Plotting final ROIs..."
                vmax = np.percentile(img, 98)
                pl.figure()
                pl.imshow(img, interpolation='None', cmap=pl.cm.gray, vmax=vmax)
                for ridx in range(len(roi_idxs)):
                    masktmp = masks[:,:,ridx]
                    msk = masktmp.copy() 
                    msk[msk==0] = np.nan
                    pl.imshow(msk, interpolation='None', alpha=0.3, cmap=pl.cm.hot)
                    [ys, xs] = np.where(masktmp>0)
                    pl.text(xs[int(round(len(xs)/4))], ys[int(round(len(ys)/4))], str(ridx+1), weight='bold')
                    pl.axis('off')
                pl.colorbar()
                pl.tight_layout()
                
                # Save image:
                imname = '%s_%s_%s_masks.png' % (roi_id, rid_hash, filenames[fidx])
                print(imname) 
                pl.savefig(os.path.join(rid_figdir, imname))
                pl.close()
                
        else:
            # do sth ?
            print "Formatting for roi_type %s unknown..." % roi_type
            
    except Exception as e:
        print "--ERROR: formatting ROIs to standard! -------------------------"
        traceback.print_exc()
        print "Unable to format ROIs for type: %s" % roi_type
        print "ABORTING."
        print "---------------------------------------------------------------"
    finally:
        maskfile.close()


#%% Clean up tmp files:

print "RID %s -- Finished formatting ROI output to standard." % rid_hash
post_rid_cleanup(session_dir, rid_hash)
print "Cleaned up tmp rid files."

#%%
print "*************************************************"
print "FINISHED EXTRACTING ROIs!"
print "*************************************************"
