#!/usr/bin/env python2
'''
This script calls MATLAB function do_bidi_correction.m

inputs : 
    sourcedir :  fullpath to dir containing tiffs to be bidi corrected
    destdir : fullpath to writedir of bidi-corrected tiffs
    A :  reference struct containing meta info about current run
'''

import os
import sys
import json
import optparse
from stat import S_IREAD, S_IRGRP, S_IROTH
import matlab.engine
import copy
from checksumdir import dirhash
from pipeline.python.set_pid_params import get_default_pid, write_hash_readonly, append_hash_to_paths
from pipeline.python.utils import sort_deinterleaved_tiffs, interleave_tiffs, deinterleave_tiffs
from memory_profiler import profile

from os.path import expanduser
home = expanduser("~")

import matlab.engine

@profile
def do_motion(options):
    parser = optparse.OptionParser()

    # PATH opts:
    parser.add_option('-R', '--root', action='store', dest='rootdir', default='/nas/volume1/2photon/data', help='source dir (root project dir containing all expts) [default: /nas/volume1/2photon/data]')
    parser.add_option('-i', '--animalid', action='store', dest='animalid', default='', help='Animal ID')
    parser.add_option('-S', '--session', action='store', dest='session', default='', help='session dir (format: YYYMMDD_ANIMALID') 
    parser.add_option('-A', '--acq', action='store', dest='acquisition', default='', help="acquisition folder (ex: 'FOV1_zoom3x')")
    parser.add_option('-r', '--run', action='store', dest='run', default='', help='name of run to process')
    parser.add_option('-p', '--pid', action='store', dest='pid_hash', default='', help="PID hash of current processing run (6 char), default will create new if set_pid_params.py not run")
    parser.add_option('-P', '--repo', action='store', dest='repo_path', default='~/Repositories/2p-pipeline', help='Path to 2p-pipeline repo. [default: ~/Repositories/2p-pipeline. If --slurm, default: /n/coxfs01/2p-pipeline/repos/2p-pipeline]')
    parser.add_option('--slurm', action='store_true', dest='slurm', default=False, help='flag to use SLURM default opts')
    parser.add_option('--motion', action='store_true', dest='do_mc', default=False, help='flag to actually do motion-correction')

    (options, args) = parser.parse_args(options) 

    rootdir = options.rootdir #'/nas/volume1/2photon/projects'
    animalid = options.animalid
    session = options.session #'20171003_JW016' #'20170927_CE059'
    acquisition = options.acquisition #'FOV1' #'FOV1_zoom3x'
    run = options.run
    pid_hash = options.pid_hash
    repo_path = options.repo_path
    slurm = options.slurm
    do_mc = options.do_mc
    if slurm is True and 'coxfs01' not in repo_path:
        repo_path = '/n/coxfs01/2p-pipeline/repos/2p-pipeline'
    if '~' in repo_path:
        repo_path = repo_path.replace('~', home)
    repo_path_matlab = os.path.join(repo_path, 'pipeline', 'matlab')
    

    # -------------------------------------------------------------
    # Set basename for files created containing meta/reference info:
    # -------------------------------------------------------------
    raw_simeta_basename = 'SI_%s' % run #functional_dir
    run_info_basename = '%s' % run #functional_dir
    pid_info_basename = 'pids_%s' % run

    # -------------------------------------------------------------
    # Set paths:
    # -------------------------------------------------------------
    acquisition_dir = os.path.join(rootdir, animalid, session, acquisition)

    tmp_pid_dir = os.path.join(acquisition_dir, run, 'processed', 'tmp_pids')
    paramspath = os.path.join(tmp_pid_dir, 'tmp_pid_%s.json' % pid_hash)
    runmeta_path = os.path.join(acquisition_dir, run, '%s.json' % run_info_basename)
    
    # -------------------------------------------------------------
    # Load run info:
    # -------------------------------------------------------------
    with open(runmeta_path, 'r') as f:
        runinfo = json.load(f)
    if len(runinfo['slices']) > 1 or runinfo['nchannels'] > 1:
        multiplanar = True
    else:
        multiplanar = False
        
    # -------------------------------------------------------------
    # Load PID:
    # -------------------------------------------------------------
    tmp_pid_fn = 'tmp_pid_%s.json' % pid_hash
    paramspath = os.path.join(tmp_pid_dir, tmp_pid_fn)
    with open(paramspath, 'r') as f:
        PID = json.load(f)
        
    # -----------------------------------------------------------------------------
    # Update SOURCE/DEST paths for current PID, if needed:
    # -----------------------------------------------------------------------------
    # Make sure preprocessing sourcedir/destdir are correct:
    PID = append_hash_to_paths(PID, pid_hash, step='motion')
    
    interleave_write_tiffs = False
    if PID['PARAMS']['motion']['method'] == 'Acquisition2P' and multiplanar is True:
        # Default is to write deinterleaved slices to write_dir
        PID['PARAMS']['motion']['destdir'] = PID['PARAMS']['motion']['destdir'] + '_slices'
        interleave_write_tiffs = True
        
    with open(paramspath, 'w') as f:
        json.dump(PID, f, indent=4, sort_keys=True)
    
    source_dir = PID['PARAMS']['motion']['sourcedir']
    write_dir = PID['PARAMS']['motion']['destdir']
    
    print "======================================================="
    print "PID: %s -- MOTION", pid_hash
    #pp.pprint(PID)
    print "SOURCE:", source_dir
    print "DEST:", write_dir
    print "======================================================="
    if not os.path.exists(write_dir):
        os.makedirs(write_dir)

    # -------------------------------------------------------------
    # Do correction:
    # -------------------------------------------------------------
    if do_mc is True:
        print "================================================="
        print "Doing MOTION correction."
        print "================================================="
        eng = matlab.engine.start_matlab()
        eng.cd(repo_path_matlab, nargout=0)
        eng.add_repo_paths(nargout=0)
        eng.do_motion_correction(paramspath, nargout=0)
        eng.quit()

    # -------------------------------------------------------------
    # Check for Interleaving/Deinterleaving:
    # -------------------------------------------------------------
    if interleave_write_tiffs is True:
        slice_dir = copy.copy(write_dir)
        volume_dir = slice_dir.split('_slices')[0]
        interleave_tiffs(slice_dir, volume_dir, runmeta_path)
    else:
        volume_dir = copy.copy(write_dir)
        slice_dir = volume_dir + '_slices'
        
    if multiplanar is True:
        print "Multiple slices/channels found. Sorting deinterleaved tiffs."
        sort_deinterleaved_tiffs(slice_dir, runmeta_path)

    # ========================================================================================
    # UPDATE PREPROCESSING SOURCE/DEST DIRS, if needed:
    # ========================================================================================
    write_hash = None
    if do_mc is True:
        write_hash, PID = write_hash_readonly(volume_dir, PID=PID, step='motion', label='mc')
        
    with open(paramspath, 'w') as f:
        print paramspath
        json.dump(PID, f, indent=4, sort_keys=True)
    # ========================================================================================

    return write_hash, pid_hash


def main(options):
    
    mc_hash, pid_hash = do_motion(options)
    
    print "PID %s: Finished motion-correction step: output dir hash %s" % (pid_hash, mc_hash)
    
if __name__ == '__main__':
    main(sys.argv[1:]) 

    