#!/usr/bin/env python2
'''
This script combines behavior/stimulation info with acquisition/frame info.

Input:
    - Raw behavior files saved in <run_dir>/raw/paradigm_files/ -- both serial data (*.txt) and protocol info (*.mwk)
    - Assumes .mwk files for behavior events and csv-saved .txt file that samples the acquisition rig at 1kHz

Steps:

1.  Creates a SINGLE parsed .json for EACH behavior file (.mwk) that contains relevant info for each trial in that file.
    - MW stimulus-presentation info is extracted with process_mw_files.py

    Output:

    a.  parsed_trials_<BEHAVIOR_FILE_NAME>.json files (1 for multiple .tifs, or 1 for each .tif if one_to_one = True)
        -- these output files are saved to: <RUN_DIR>/paradigm/files/
        -- (OPTIONAL: also can create a stimorder.txt file for EACH .tif to be aligned (option if not using .mwk), for align_acquisition_events.py)

2.  Aligns image-acquisition events (serial data stored in .txt files) with behavior events using the parsed behavior info from Step 1.
    All trials are combined across all .tif files and behavior (i.e., 'aux') files and creates dictionary for each trial in the whole run (collapses across blocks).

    Output:

    a.  trials_<TRILAINFO_HASH>.json (SINGLE file)
        -- this file is saved to:  <RUN_DIR>/paradigm/
        -- each dict in this file is of format:

            'trial00001': {
                    'trial_hash'         :  hash created for entire trial dictionary in input parsed-trials file (from Step 1)
                    'block_idx'          :  tif file index in run (i..e, block number, 0-indexed)
                    'ntiffs_per_auxfile' :  total number of tiffs associated with this AUX file
                    'behavior_data_path' :  path to input files containing pasred trial info for each behavior file (from Step 1)
                    'serial_data_path'   :  path to input files containing serial data for each frame acquired frame
                    'start_time_ms'      :  trial start time (in msec) relative to start of run (i.e., when SI frame-trigger received)
                    'end_time_ms'        :  trial end time (ms) relative to start of run
                    'stim_dur_ms'        :  duration of stim on
                    'iti_dur_ms'         :  duration of ITI period after stim offset
                    'stimuli'            :  stimulus-info dict from MW, of format:
                            {
                            'filepath'   :  path to stimulus on stimulation computer
                            'filehash'   :  file hash of shown stimulus
                            'position'   :  x,y position (tuple of floats),
                            'rotation'   :  rotation specified by protocol (float),
                            'scale'      :  x,y size of stimulus (tuple of floats),
                            'stimulus'   :  name or index of shown stimulus,
                            'type'       :  type of stimulus (e.g., image, drifting_grating)
                            }
                    'trial_in_run'       :  index (1-indexed) of current trial across whole run (across all behavior files, if multiple exist),
                    'frame_stim_on'      :  index (0-indexed) of the closest-matching frame to stimulus onset (index in .tif)
                    'frame_stim_off'     :  index (0-indexed) of frame at which stimulus goes off
                    }

Notes:

This output is used by align_acquisition_events.py to use the frame_stim_on and frame_stim_off for each trial across all files,
combined with a user-specified baseline period (default, 1 sec) to get trial-epoch aligned frame indices.
'''

import os
import sys
import json
import re
import hashlib
import optparse
import shutil
import numpy as np
import pandas as pd
import cPickle as pkl
from collections import Counter
from pipeline.python.paradigm import process_mw_files as mw
from pipeline.python.utils import hash_file

def atoi(text):
    return int(text) if text.isdigit() else text

def natural_keys(text):
    return [ atoi(c) for c in re.split('(\d+)', text) ]

#%%

def extract_frames_to_trials(serialfn_path, mwtrial_path, framerate, verbose=False):

    trialevents = None

    ### LOAD MW DATA.
    with open(mwtrial_path, 'r') as f:
        mwtrials = json.load(f)

    ### LOAD SERIAL DATA.
    serialdata = pd.read_csv(serialfn_path, sep='\t')
    if verbose is True:
        print serialdata.columns

    ### Extract events from serialdata:
    frame_triggers = serialdata[' frame_trigger']
    bitcodes = serialdata[' pixel_clock']

    ### Find frame ON triggers (from NIDAQ-SI):
    frame_on_idxs = [idx+1 for idx,diff in enumerate(np.diff(frame_triggers)) if diff==1]
    frame_on_idxs.append(0)
    frame_on_idxs = sorted(frame_on_idxs)
    # Check that no frame triggers were skipped/missed:
    diffs = np.diff(frame_on_idxs)
    nreads_per_frame = max(set(diffs), key=list(diffs).count)
    print "Found %i frame-triggers." % len(frame_on_idxs)


    ### Get arduino-processed bitcodes for each frame: frame_on_idxs[8845]
    frame_bitcodes = dict()
    for idx,frameidx in enumerate(frame_on_idxs):
        #framenum = 'frame'+str(idx)
        if idx==len(frame_on_idxs)-1:
            bcodes = bitcodes[frameidx:]
        else:
            bcodes = bitcodes[frameidx:frame_on_idxs[idx+1]]
        frame_bitcodes[idx] = bcodes


    ### Find first frame of MW experiment start:
    modes_by_frame = dict()
    for frame in frame_bitcodes.keys():
        bitcode_counts = Counter(frame_bitcodes[frame])
        modes_by_frame[frame] = bitcode_counts.most_common(1)[0][0]

    # Take the 2nd frame that has the first-stim value (in case bitcode of Image on Trial1 is 0):
    trialnames = sorted(mwtrials.keys(), key=natural_keys)
    if 'grating' in mwtrials[trialnames[0]]['stimuli']['type']:
        first_stim_frame = [k for k in sorted(modes_by_frame.keys()) if modes_by_frame[k]>0][0]
    else:
        first_stim_frame = [k for k in sorted(modes_by_frame.keys()) if modes_by_frame[k]>0][1] #[0]


    ### Get all bitcodes and corresonding frame-numbers for each trial:
    trialevents = dict()
    allframes = sorted(frame_bitcodes.keys()) #, key=natural_keys)
    curr_frames = sorted(allframes[first_stim_frame+1:]) #, key=natural_keys)
    first_frame = first_stim_frame


    for tidx, trial in enumerate(sorted(mwtrials.keys(), key=natural_keys)): #[0:46]):
        #print trial
        # Create hash of current MWTRIAL dict:
        mwtrial_hash = hashlib.sha1(json.dumps(mwtrials[trial], sort_keys=True)).hexdigest()


        #print trial
        trialevents[mwtrial_hash] = dict()
        #trialevents[trial]['mwtrial_hash'] = mwtrial_hash
        #trialevents[trial]['stiminfo'] = mwtrials[trial]['stimuli']
        trialevents[mwtrial_hash]['stim_dur_ms'] = mwtrials[trial]['stim_off_times'] - mwtrials[trial]['stim_on_times']
        #trialevents[trial]['iti_dur_ms'] = mwtrials[trial]['iti_duration']

        if int(tidx+1)>1:
        	    # Skip a good number of frames from the last "found" index of previous trial.
        	    # Since ITI is long (relative to framerate), this is safe to do. Avoids possibility that
        	    # first bitcode of trial N happened to be last stimulus bitcode of trial N-1
        	    nframes_to_skip = int(((mwtrials[trial]['iti_duration']/1E3) * framerate) - 3)
        	    #print 'skipping iti...', nframes_to_skip
        	    curr_frames = allframes[first_frame+nframes_to_skip:]

        first_found_frame = [] #8542 [(14, 8547), (6, 8592)]
        minframes = 4
        for bitcode in mwtrials[trial]['all_bitcodes']:
            looking = True
            while looking is True:
                for frame in sorted(curr_frames):
                    tmp_frames = [i for i in frame_bitcodes[frame] if i==bitcode]
                    consecutives = [i for i in np.diff(tmp_frames) if i==0]

                    if frame>1:
                        tmp_frames_pre = [i for i in frame_bitcodes[int(frame)-1] if i==bitcode]
                        consecutives_pre = [i for i in np.diff(tmp_frames_pre) if i==0]

                    if len(mwtrials[trial]['all_bitcodes'])<3:
                    #Single-image (static images) will only have a single bitcode, plus ITI bitcode,
                        # Don't look before/after found-frame idx.
                        if len(consecutives)>=minframes:
                            first_frame = frame
                            looking = False

                    else:
                        if frame>1 and len(consecutives_pre)>=minframes:
                            if len(consecutives_pre) > len(consecutives):
                                first_frame = int(frame) - 1
                            elif len(consecutives)>=minframes:
                                first_frame = int(frame)
                            #print "found2...", bitcode, first_frame #len(curr_frames)
                            looking = False

                        elif len(consecutives)>=minframes:
                            first_frame = frame
                            #print "found...", bitcode, first_frame #len(curr_frames)
                            looking = False

                    if looking is False:
                        break

            first_found_frame.append((bitcode, first_frame)) #first_frame))
            curr_frames = allframes[first_frame+1:] #curr_frames[idx:] #curr_frames[first_frame:]

        #if (first_found_frame[-1][1] - first_found_frame[0][1])/framerate > 2.5:
        #print "Trial %i dur (s):" % int(trial)
        print (first_found_frame[-1][1] - first_found_frame[0][1])/framerate, '[%s]' % trial

        trialevents[mwtrial_hash]['stim_on_idx'] = first_found_frame[0][1]
        trialevents[mwtrial_hash]['stim_off_idx'] = first_found_frame[-1][1]
        trialevents[mwtrial_hash]['mw_trial'] = mwtrials[trial]

    return trialevents
#%%

def extract_options(options):
    parser = optparse.OptionParser()

    parser.add_option('-D', '--root', action='store', dest='rootdir', default='/nas/volume1/2photon/data', help='data root dir (root project dir containing all animalids) [default: /nas/volume1/2photon/data, /n/coxfs01/2pdata if --slurm]')
    parser.add_option('-i', '--animalid', action='store', dest='animalid', default='', help='Animal ID')

    # Set specific session/run for current animal:
    parser.add_option('-S', '--session', action='store', dest='session', default='', help='session dir (format: YYYMMDD_ANIMALID')
    parser.add_option('-A', '--acq', action='store', dest='acquisition', default='FOV1', help="acquisition folder (ex: 'FOV1_zoom3x') [default: FOV1]")
    parser.add_option('-R', '--run', action='store', dest='run', default='', help="name of run dir containing tiffs to be processed (ex: gratings_phasemod_run1)")
    parser.add_option('--slurm', action='store_true', dest='slurm', default=False, help="set if running as SLURM job on Odyssey")


    parser.add_option('--retinobar', action="store_true",
                      dest="retinobar", default=False, help="Set flag if stimulus is moving-bar for retinotopy.")
    parser.add_option('--phasemod', action="store_true",
                      dest="phasemod", default=False, help="Set flag if using dynamic, phase-modulated gratings.")
    parser.add_option('-t', '--triggervar', action="store",
                      dest="frametrigger_varname", default='frame_trigger', help="Temp way of dealing with multiple trigger variable names [default: frame_trigger]")
    parser.add_option('--multi', action="store_false",
                      dest="single_run", default=True, help="Set flag if multiple start/stops in run.")

    (options, args) = parser.parse_args(options)

    return options

#%%
#rootdir = '/mnt/odyssey'
#animalid = 'CE074'
#session = '20180215'
#acquisition = 'FOV2_zoom1x_LI'
#run = 'blobs'
#slurm = False
#retinobar = False
#phasemod = False
#trigger_varname = 'frame_trigger'
#stimorder_files = False


def parse_acquisition_events(run_dir):

    run = os.path.split(run_dir)[-1]
    runinfo_path = os.path.join(run_dir, '%s.json' % run)

    with open(runinfo_path, 'r') as fr:
        runinfo = json.load(fr)
    nfiles = runinfo['ntiffs']
    file_names = sorted(['File%03d' % int(f+1) for f in range(nfiles)], key=natural_keys)

    #%%

    # Set outpath to save trial info file for whole run:
    outdir = os.path.join(run_dir, 'paradigm')

    #%%
    # =============================================================================
    # Get SERIAL data:
    # =============================================================================
    paradigm_rawdir = os.path.join(run_dir, runinfo['rawtiff_dir'], 'paradigm_files')
    serialdata_fns = sorted([s for s in os.listdir(paradigm_rawdir) if s.endswith('txt') if 'serial' in s], key=natural_keys)
    print "Found %02d serial-data files, and %i TIFFs." % (len(serialdata_fns), nfiles)

    if len(serialdata_fns) < nfiles:
        one_to_one = False
    else:
        one_to_one = True

    # Load MW info:
    paradigm_outdir = os.path.join(run_dir, 'paradigm', 'files')
    mwtrial_fns = sorted([j for j in os.listdir(paradigm_outdir) if j.endswith('json') and 'parsed_' in j], key=natural_keys)
    print "Found %02d MW files, and %02d ARD files." % (len(mwtrial_fns), len(serialdata_fns))


    #%%
    # =============================================================================
    # Create <RUN_DIR>/paradigm/trials_<TRIALINFO_HASH>.json file
    # =============================================================================
    RUN = dict()
    trialnum = 0
    for fid,serialfn in enumerate(sorted(serialdata_fns, key=natural_keys)):

        framerate = 44.68 #float(runinfo['frame_rate'])

        currfile = "File%03d" % int(fid+1)

        print "================================="
        print "Processing files:"
        print "MW: ", mwtrial_fns[fid]
        print "ARD: ", serialdata_fns[fid]
        print "---------------------------------"

        # Load MW parsed trials:
        mwtrial_path = os.path.join(paradigm_outdir, mwtrial_fns[fid])

        # Load Acquisition serialdata info:
        serialfn_path = os.path.join(paradigm_rawdir, serialfn)

        # Align MW events to frame-events from serialdata:
        trialevents = extract_frames_to_trials(serialfn_path, mwtrial_path, framerate, verbose=False)

        # Sort trials in run by time:
        sorted_trials_in_run = sorted(trialevents.keys(), key=lambda x: trialevents[x]['stim_on_idx'])
        sorted_stim_frames = [(trialevents[t]['stim_on_idx'], trialevents[t]['stim_off_idx']) for t in sorted_trials_in_run]

        # Create a dictionary for each trial in the run that specifies ALL info:
        # SI info:
        #     - frame indices for sitm ON/OFF
        #     - meta info (block number in run, ntiffs per behavior file, etc.)
        # AUX info:
        #     - stimulus info (from MW)
        #     - stimulus presentation info
        # META info:
        #     - paths to MW and serial data info that are the source of this dict's contents
        trialnum = 0
        for trialhash in sorted_trials_in_run:
            trialnum += 1
            trialname = 'trial%05d' % int(trialnum)

            RUN[trialname] = dict()
            RUN[trialname]['trial_hash'] = trialhash
            RUN[trialname]['block_idx'] = trialevents[trialhash]['mw_trial']['block_idx']
            if one_to_one is True:
                RUN[trialname]['ntiffs_per_auxfile'] = 1
            else:
                RUN[trialname]['ntiffs_per_auxfile'] = nfiles
            RUN[trialname]['behavior_data_path'] = mwtrial_path
            RUN[trialname]['serial_data_path'] = serialfn_path

            RUN[trialname]['start_time_ms'] = trialevents[trialhash]['mw_trial']['start_time_ms']
            RUN[trialname]['end_time_ms'] = trialevents[trialhash]['mw_trial']['end_time_ms']
            RUN[trialname]['stim_dur_ms'] = trialevents[trialhash]['mw_trial']['stim_off_times']\
                                                    - trialevents[trialhash]['mw_trial']['stim_on_times']
            RUN[trialname]['iti_dur_ms'] = trialevents[trialhash]['mw_trial']['iti_duration']
            RUN[trialname]['stimuli'] = trialevents[trialhash]['mw_trial']['stimuli']

            RUN[trialname]['frame_stim_on'] = trialevents[trialhash]['stim_on_idx']
            RUN[trialname]['frame_stim_off'] = trialevents[trialhash]['stim_off_idx']
            RUN[trialname]['trial_in_run'] = trialnum


    # Get unique hash for current RUN dict:
    run_trial_hash = hashlib.sha1(json.dumps(RUN, indent=4, sort_keys=True)).hexdigest()[0:6]

    # Move old files to subdir 'old' so that there is no confusion with hashed files:
    existing_files = [f for f in os.listdir(outdir) if 'trials_' in f and f.endswith('json') and run_trial_hash not in f]
    if len(existing_files) > 0:
        old = os.path.join(os.path.split(outdir)[0], 'paradigm', 'old')
        if not os.path.exists(old):
            os.makedirs(old)
        for f in existing_files:
            shutil.move(os.path.join(outdir, f), os.path.join(old, f))

    parsed_run_outfile = os.path.join(outdir, 'trials_%s.json' % run_trial_hash)
    with open(parsed_run_outfile, 'w') as f:
        json.dump(RUN, f, sort_keys=True, indent=4)

    return parsed_run_outfile


def main(options):
    # ================================================================================
    # MW trial extraction:
    # ================================================================================
    options = extract_options(options)

    # Set USER INPUT options:
    rootdir = options.rootdir
    animalid = options.animalid
    session = options.session
    acquisition = options.acquisition
    run = options.run
    slurm = options.slurm

    if slurm is True and 'coxfs01' not in rootdir:
        rootdir = '/n/coxfs01/2p-data'

    # MW specific options:
    retinobar = options.retinobar
    phasemod = options.phasemod
    trigger_varname = options.frametrigger_varname
    single_run = options.single_run

    stimorder_files = False #True

    mwopts = ['-D', rootdir, '-i', animalid, '-S', session, '-A', acquisition, '-R', run, '-t', trigger_varname]
    if slurm is True:
        mwopts.extend(['--slurm'])
    if retinobar is True:
        mwopts.extend(['--retinobar'])
    if phasemod is True:
        mwopts.extend(['--phasemod'])
    if single_run is False:
        mwopts.extend(['--multi'])

    #%
    paradigm_outdir = mw.parse_mw_trials(mwopts)
    print "----------------------------------------"
    print "Extracted MW events!"
    print "Outfile saved to:\n%s" % paradigm_outdir
    print "----------------------------------------"

    #%
    if stimorder_files is True:
        mw.create_stimorder_files(paradigm_outdir)

    # Set reference path and get SERIALDATA info:
    # ================================================================================
    run_dir = os.path.join(rootdir, animalid, session, acquisition, run)
    parsed_run_outfile = parse_acquisition_events(run_dir)
    print "----------------------------------------"
    print "ACQUISITION INFO saved to:\n%s" % parsed_run_outfile
    print "----------------------------------------"


if __name__ == '__main__':
    main(sys.argv[1:])

