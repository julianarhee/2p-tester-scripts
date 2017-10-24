#!/usr/bin/env python2
'''
python files_to_trials.py -h for opts.

Requires stimdict containing relevant frame indices for each trial:
    - output of create_stimdict.py
    - <path_to_paradigm_files>/stimdict.pkl (.json)

Requires stimorder file (1 for all files, or 1 for each file):
    - order of stimuli (by IDX) in a given TIFF file
    - output of extract_acquisition_events.py
    - <path_to_paradigm_files>/stimorder_FileXXX.txt (or: stim_order.txt)


Requires tracestruct containing traces (frames_in_files x nrois matrix) for each file:
    - output of get_rois_and_traces step of run_pipeline.m (MATLAB)
    - <path_to_analysis_specific_trace_structs>/traces_SliceXX_ChannelXX.mat

OUTPUTS:
    - stimtraces dicts :  traces-by-roi for each trial (list of arrays) for each stimulus 
    - <path_to_analysis_specific_trace_structs>/Parsed/stimtraces_ChannelXX_SliceXX.mat (.json, .pkl)




'''

import os
import json
import re
import scipy.io as spio
import numpy as np
from json_tricks.np import dump, dumps, load, loads
from mat2py import loadmat
import cPickle as pkl
import scipy.io
import optparse

def atoi(text):
    return int(text) if text.isdigit() else text

def natural_keys(text):
    return [ atoi(c) for c in re.split('(\d+)', text) ]

class StimInfo:
    def _init_(self):
        self.stimid = ''
        self.trials = []
        self.frames = []
        self.frames_sec = []
        self.stim_on_idx = []

def serialize_json(instance=None, path=None):
    dt = {}
    dt.update(vars(instance))

 
parser = optparse.OptionParser()
parser.add_option('-S', '--source', action='store', dest='source', default='/nas/volume1/2photon/projects', help='source dir (root project dir containing all expts) [default: /nas/volume1/2photon/projects]')
parser.add_option('-E', '--experiment', action='store', dest='experiment', default='', help='experiment type (parent of session dir)') 
parser.add_option('-s', '--session', action='store', dest='session', default='', help='session dir (format: YYYMMDD_ANIMALID') 
parser.add_option('-A', '--acq', action='store', dest='acquisition', default='', help="acquisition folder (ex: 'FOV1_zoom3x')")
parser.add_option('-f', '--functional', action='store', dest='functional_dir', default='functional', help="folder containing functional TIFFs. [default: 'functional']")

parser.add_option('-I', '--id', action="store",
                  dest="analysis_id", default='', help="analysis_id (includes mcparams, roiparams, and ch). see <acquisition_dir>/analysis_record.json for help.")

parser.add_option('-O', '--stimon', action="store",
                  dest="stim_on_sec", default='', help="Time (s) stimulus ON.")

# parser.add_option('-c', '--channel', action="store",
#                   dest="selected_channel", default=1, help="Channel idx of signal channel. [default: 1]")
# 

(options, args) = parser.parse_args() 


source = options.source #'/nas/volume1/2photon/projects'
experiment = options.experiment #'scenes' #'gratings_phaseMod' #'retino_bar' #'gratings_phaseMod'
session = options.session #'20171003_JW016' #'20170927_CE059' #'20170902_CE054' #'20170825_CE055'
acquisition = options.acquisition #'FOV1' #'FOV1_zoom3x' #'FOV1_zoom3x_run2' #'FOV1_planar'
functional_dir = options.functional_dir #'functional' #'functional_subset'

#roi_method = options.roi_method
analysis_id = options.analysis_id

stim_on_sec = float(options.stim_on_sec) #2. # 0.5
#selected_channel = int(options.selected_channel)


# source = '/nas/volume1/2photon/projects'
# # experiment = 'scenes'
# # session = '20171003_JW016'
# # acquisition = 'FOV1'
# # functional_dir = 'functional'

# experiment = 'gratings_phaseMod'
# session = '20171009_CE059'
# acquisition = 'FOV1_zoom3x'
# functional_dir = 'functional'
 
# ================================================================================
# frame info:
# ================================================================================
#first_frame_on = 50
#stim_on_sec = 2. #0.5
#iti = 1.
#vols_per_trial = 15
#same_order = True
# =================================================================================


acquisition_dir = os.path.join(source, experiment, session, acquisition)
figdir = os.path.join(acquisition_dir, 'example_figures')


# Load reference info:
ref_json = 'reference_%s.json' % functional_dir 
with open(os.path.join(acquisition_dir, ref_json), 'r') as fr:
    ref = json.load(fr)


# Load SI meta data:
si_basepath = ref['raw_simeta_path'][0:-4]
simeta_json_path = '%s.json' % si_basepath
with open(simeta_json_path, 'r') as fs:
    simeta = json.load(fs)

file_names = sorted([k for k in simeta.keys() if 'File' in k], key=natural_keys)
nfiles = len(file_names)


# Get ROIPARAMS: 
roi_dir = os.path.join(ref['roi_dir'], ref['roi_id'][analysis_id]) #, 'ROIs')
roiparams = loadmat(os.path.join(roi_dir, 'roiparams.mat'))
if 'roiparams' in roiparams.keys():
    roiparams = roiparams['roiparams']
    # maskpaths = roiparams['roiparams']['maskpaths']
maskpaths = roiparams['maskpaths']
if not isinstance(maskpaths, list):
    maskpaths = [maskpaths]


# Check slices to see if maskpaths exist for all slices, or just a subset:
if 'sourceslices' in roiparams.keys():
    slices = roiparams['sourceslices']
    print "USING SPECIFIED SOURCE SLICES."
else:
    slices = ref['slices']
if isinstance(slices, int):
    slices = [slices]
#     slices = range(len(maskpaths))
#     slices = [s+1 for s in slices]
print "Found masks for slices:", slices


# Load trace structs:
selected_channel = int(ref['signal_channel'][analysis_id])
trace_dir = os.path.join(ref['trace_dir'], ref['trace_id'][analysis_id]) #, roi_method)
currchannel = "Channel%02d" % int(selected_channel)
curr_tracestruct_fns = os.listdir(trace_dir)
trace_fns_by_slice = sorted([t for t in curr_tracestruct_fns if 'traces_Slice' in t and currchannel in t], key=natural_keys)
if len(trace_fns_by_slice)==0:
    print "No trace structs found for Channel %i." % int(selected_channel)
print trace_fns_by_slice


# Get PARADIGM INFO:
path_to_functional = os.path.join(acquisition_dir, functional_dir)
paradigm_dir = 'paradigm_files'
path_to_paradigm_files = os.path.join(path_to_functional, paradigm_dir)


# Load stimulus dict:
stimdict_fn = 'stimdict.pkl'
with open(os.path.join(path_to_paradigm_files, stimdict_fn), 'r') as f:
     stimdict = pkl.load(f) #json.load(f)
#print "STIMDICT: ", sorted(stimdict.keys(), key=natural_keys)


# Create parsed-trials dir with default format:
parsed_traces_dir = os.path.join(trace_dir, 'Parsed')
if not os.path.exists(parsed_traces_dir):
    os.mkdir(parsed_traces_dir)


# Get num trials for each stimulus (combine across files):
stim_ntrials = dict()
for stim in stimdict.keys():
    stim_ntrials[stim] = 0
    for fi in stimdict[stim].keys():
        stim_ntrials[stim] += len(stimdict[stim][fi].trials)



# Split all traces by stimulus-ID:
# ----------------------------------------------------------------------------

stimtraces_all_slices = dict()

for slice_idx,trace_fn in enumerate(sorted(trace_fns_by_slice, key=natural_keys)):

    print "EXTRACING FROM:", trace_fn
    currslice = "Slice%02d" % int(slices[slice_idx]) # int(slice_idx+1)
    stimtraces = dict((stim, dict()) for stim in stimdict.keys())

    tracestruct = loadmat(os.path.join(trace_dir, trace_fn))
    
    # To look at all traces for ROI 3 for stimulus 1:
    # traces_by_stim['1']['Slice01'][:,roi,:]
    for stim in sorted(stimdict.keys(), key=natural_keys):
        #stimtraces[stim] = dict()
        repidx = 0
        raw_traces_allrois = []
        curr_traces_allrois = []
        curr_frames_allrois = []
        stim_on_frames = []
        for fi,currfile in enumerate(sorted(file_names, key=natural_keys)):
#            nframes = int(simeta[currfile]['SI']['hFastZ']['numVolumes'])
#            framerate = float(simeta[currfile]['SI']['hRoiManager']['scanFrameRate'])
            volumerate = float(simeta[currfile]['SI']['hRoiManager']['scanVolumeRate'])
#            frames_tsecs = np.arange(0, nframes)*(1/volumerate)

            nframes_on = stim_on_sec * volumerate #nt(round(stim_on_sec * volumerate))
#            nframes_off = vols_per_trial - nframes_on
#            frames_iti = round(iti * volumerate) 
            curr_ntrials = len(stimdict[stim][currfile].frames)
	    rawtraces = tracestruct['file'][fi].rawtracemat
	    currtraces = tracestruct['file'][fi].tracematDC

	    #print currtraces.shape
            for currtrial_idx in range(curr_ntrials):
                #print stimdict[stim][currfile].frames[currtrial_idx]
                currtrial_frames = stimdict[stim][currfile].frames[currtrial_idx]
                currtrial_frames = [int(i) for i in currtrial_frames] 
		#print "CURRTRIAL FRAMES:", currtrial_frames
		#print len(currtrial_frames)
   
                # .T to make rows = rois, cols = frames 
                nframes = currtraces.shape[0]
                nrois = currtraces.shape[1] 
		#print nframes, nrois, currtrial_frames.shape
                #print currtraces.shape
                raw_traces_allrois.append(rawtraces[currtrial_frames, :]) 
	        curr_traces_allrois.append(currtraces[currtrial_frames, :])
                curr_frames_allrois.append(currtrial_frames)
                repidx += 1
                #print stimdict[stim][currfile].stim_on_idx 
                curr_frame_onset = stimdict[stim][currfile].stim_on_idx[currtrial_idx]
                stim_on_frames.append([curr_frame_onset, curr_frame_onset + nframes_on])
                
        check_stimname = list(set(stimdict[stim][currfile].stimid))
        if len(check_stimname)>1:
            print "******************************"
            print "Bad Stim to Trial parsing!."
            print "------------------------------"
            print check_stimname
            print "STIM:", stim, "File:", currfile
            print "------------------------------"
            print "Check extract_acquisition_events.py and create_stimdict.py"
            print "******************************"
        else:
	    #print check_stimname
            stimname = check_stimname[0]
        
        stimtraces[stim]['name'] = stimname
        stimtraces[stim]['traces'] = np.asarray(curr_traces_allrois)
        stimtraces[stim]['raw_traces'] = np.asarray(raw_traces_allrois)
    	stimtraces[stim]['frames_stim_on'] = stim_on_frames 
	# print stimtraces[stim]['frames_stim_on']
        stimtraces[stim]['frames'] = np.asarray(curr_frames_allrois)
        stimtraces[stim]['ntrials'] = stim_ntrials[stim]
        stimtraces[stim]['nrois'] = nrois


    curr_stimtraces_json = 'stimtraces_%s_%s.json' % (currslice, currchannel)
    print curr_stimtraces_json
    with open(os.path.join(parsed_traces_dir, curr_stimtraces_json), 'w') as f:
        dump(stimtraces, f, indent=4)


    curr_stimtraces_pkl = 'stimtraces_%s_%s.pkl' % (currslice, currchannel)
    print curr_stimtraces_pkl
    with open(os.path.join(parsed_traces_dir, curr_stimtraces_pkl), 'wb') as f:
        pkl.dump(stimtraces, f, protocol=pkl.HIGHEST_PROTOCOL)


    # save as .mat:
    curr_stimtraces_mat = 'stimtraces_%s_%s.mat' % (currslice, currchannel)
    # scipy.io.savemat(os.path.join(source_dir, condition, tif_fn), mdict=pydict)
    stimtraces_mat = dict()
    for stim in sorted(stimdict.keys(), key=natural_keys):
        currstim = "stim%02d" % int(stim)
        #print currstim
        stimtraces_mat[currstim] = stimtraces[stim]

    scipy.io.savemat(os.path.join(parsed_traces_dir, curr_stimtraces_mat), mdict=stimtraces_mat)
    print os.path.join(parsed_traces_dir, curr_stimtraces_mat)
  
     
    stimtraces_all_slices[currslice] = stimtraces
    stimtraces_all_fn = 'all_stimtraces_%s.pkl' % currchannel
    with open(os.path.join(parsed_traces_dir, stimtraces_all_fn), 'wb') as f:
        pkl.dump(stimtraces_all_slices, f, protocol=pkl.HIGHEST_PROTOCOL)
 

