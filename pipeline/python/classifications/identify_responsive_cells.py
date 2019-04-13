#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Fri Mar 22 17:28:03 2019

@author: julianarhee
"""

import os
import glob
import json
import copy
import pylab as pl
import seaborn as sns
import cPickle as pkl
import numpy as np
import scipy as sp
from scipy import stats
import pandas as pd
from mpl_toolkits.axes_grid1 import AxesGrid
from pipeline.python.utils import natural_keys, label_figure
from mpl_toolkits.axes_grid1 import make_axes_locatable

#%%
visual_area = ''
segment = False


#rootdir = '/n/coxfs01/2p-data'
#animalid = 'JC070' #'JC059'
#session = '20190315' #'20190227'
#fov = 'FOV1_zoom2p0x' #'FOV4_zoom4p0x'
#run = 'combined_blobs_static'
#traceid = 'traces001' #'traces001'

#rootdir = '/n/coxfs01/2p-data'
#animalid = 'JC067' 
#session = '20190319' #'20190319'
#fov = 'FOV1_zoom2p0x' 
#run = 'combined_blobs_static'
#traceid = 'traces001' #'traces002'

#rootdir = '/n/coxfs01/2p-data'
#animalid = 'JC073' #'JC059'
#session = '20190327' #'20190227'
#fov = 'FOV1_zoom2p0x' #'FOV4_zoom4p0x'
#run = 'combined_blobs_static'
#traceid = 'traces001' #'traces001'
#segment = False
#visual_area = ''

#rootdir = '/n/coxfs01/2p-data'
#animalid = 'JC059' #'JC059'
#session = '20190227' #'20190227'
#fov = 'FOV4_zoom4p0x' #'FOV4_zoom4p0x'
#run = 'combined_blobs_static'
#traceid = 'traces001' #'traces001'


rootdir = '/n/coxfs01/2p-data'
animalid = 'JC076' #'JC059'
session = '20190410' #'20190227'
fov = 'FOV1_zoom2p0x' #'FOV4_zoom4p0x'
run = 'combined_gratings_static'
traceid = 'traces001' #'traces001'
segment = False
visual_area = ''


fov_dir = os.path.join(rootdir, animalid, session, fov)
traceid_dir = glob.glob(os.path.join(fov_dir, run, 'traces', '%s*' % traceid))[0]
data_fpath = glob.glob(os.path.join(traceid_dir, 'data_arrays', '*.npz'))[0]
dset = np.load(data_fpath)
dset.keys()

data_identifier = '|'.join([animalid, session, fov, run, traceid, visual_area])
print data_identifier


#%%

included_rois = []
if segment:
    segmentations = glob.glob(os.path.join(fov_dir, 'visual_areas', '*.pkl'))
    assert len(segmentations) > 0, "Specified to segment, but no segmentation file found in acq. dir!"
    if len(segmentations) == 1:
        segmentation_fpath = segmentations[0]
    else:
        for si, spath in enumerate(sorted(segmentations, key=natural_keys)):
            print si, spath
        sel = input("Select IDX of seg file to use: ")
        segmentation_fpath = sorted(segmentations, key=natural_keys)[sel]
    with open(segmentation_fpath, 'rb') as f:
        seg = pkl.load(f)
            
    included_rois = seg.regions[visual_area]['included_rois']
    print "Found %i rois in visual area %s" % (len(included_rois), visual_area)

#%%

# Set dirs:
try:
    sorting_subdir = 'response_stats'
    sorted_dir = sorted(glob.glob(os.path.join(traceid_dir, '%s*' % sorting_subdir)))[-1]
except Exception as e:
    sorting_subdir = 'sorted_rois'
    sorted_dir = sorted(glob.glob(os.path.join(traceid_dir, '%s*' % sorting_subdir)))[-1]
print "Selected stats results: %s" % os.path.split(sorted_dir)[-1]

# Set output dir:
output_dir = os.path.join(sorted_dir, 'visualization')
if segment:
    output_dir = os.path.join(sorted_dir, 'visualization', visual_area)
if not os.path.exists(output_dir):
    os.makedirs(output_dir)
print "Saving output to:", output_dir

#%%

# Load parsed data:
trace_type = 'corrected'
traces = dset[trace_type]
zscores = dset['zscore']

# Format condition info:
aspect_ratio = 1.747
sdf = pd.DataFrame(dset['sconfigs'][()]).T
sdf['size'] = [round(sz/aspect_ratio, 1) for sz in sdf['size']]
labels = pd.DataFrame(data=dset['labels_data'], columns=dset['labels_columns'])

# Load roi stats:    
stats_fpath = glob.glob(os.path.join(sorted_dir, 'roistats_results.npz'))[0]
rstats = np.load(stats_fpath)
rstats.keys()

#%%
if segment and len(included_rois) > 0:
    all_rois = np.array(copy.copy(included_rois))
else:
    all_rois = np.arange(0, rstats['nrois_total'])

visual_rois = np.array([r for r in rstats['sorted_visual'] if r in all_rois])
selective_rois = np.array([r for r in rstats['sorted_selective'] if r in all_rois])

print "Found %i cells that pass responsivity test (%s, p<%.2f)." % (len(visual_rois), rstats['responsivity_test'], rstats['visual_pval'])
print "Found %i cells that pass responsivity test (%s, p<%.2f)." % (len(selective_rois), rstats['selectivity_test'], rstats['selective_pval'])

del rstats


#%%

raw_traces = pd.DataFrame(traces) #, index=zscored_traces.index)

# Get single value for each trial and sort by config:
trials_by_cond = dict()
for k, g in labels.groupby(['config']):
    trials_by_cond[k] = sorted([int(tr[5:])-1 for tr in g['trial'].unique()])
del traces

# zscore the traces:
# -----------------------------------------------------------------------------
zscored_traces_list = []
for trial, tmat in labels.groupby(['trial']):
    #print trial    
    stim_on_frame = tmat['stim_on_frame'].unique()[0]
    nframes_on = tmat['nframes_on'].unique()[0]
    curr_traces = raw_traces.iloc[tmat.index] ##traces[tmat.index, :]
    bas_std = curr_traces.iloc[0:stim_on_frame].std(axis=0)
    #curr_zscored_traces = pd.DataFrame(curr_traces, index=tmat.index).divide(bas_std, axis='columns')
    curr_zscored_traces = pd.DataFrame(curr_traces).divide(bas_std, axis='columns')
    zscored_traces_list.append(curr_zscored_traces)
zscored_traces = pd.concat(zscored_traces_list, axis=0)

zscores_by_cond = dict()
for cfg, trial_ixs in trials_by_cond.items():
    zscores_by_cond[cfg] = zscored_traces.iloc[trial_ixs]  # For each config, array of size ntrials x nrois


zscored_traces.head()

    
#%

# Sort ROIs by zscore by cond
# -----------------------------------------------------------------------------


avg_zscores_by_cond = pd.DataFrame([zscores_by_cond[cfg].mean(axis=0) \
                                    for cfg in sorted(zscores_by_cond.keys(), key=natural_keys)]) # nconfigs x nrois

    
# Sort mean (or max) zscore across trials for each config, and find "best config"
visual_max_avg_zscore = np.array([avg_zscores_by_cond[rid].max() for rid in visual_rois])
visual_sort_by_max_zscore = np.argsort(visual_max_avg_zscore)[::-1]
sorted_visual = visual_rois[visual_sort_by_max_zscore]

selective_max_avg_zscore = np.array([avg_zscores_by_cond[rid].max() for rid in selective_rois])
selective_sort_by_max_zscore = np.argsort(selective_max_avg_zscore)[::-1]
sorted_selective = selective_rois[selective_sort_by_max_zscore]

print [r for r in sorted_selective if r not in sorted_visual]

print sorted_selective[0:10]

#%

# Get SNR
# -----------------------------------------------------------------------------
bas_means = np.vstack([raw_traces.iloc[trial_indices.index][0:stim_on_frame].mean(axis=0) \
                       for trial, trial_indices in labels.groupby(['trial'])])
stim_means = np.vstack([raw_traces.iloc[trial_indices.index][stim_on_frame:(stim_on_frame+nframes_on)].mean(axis=0) \
                       for trial, trial_indices in labels.groupby(['trial'])])
snrs = stim_means/bas_means
  

#sizes = sorted(sdf['size'].unique())
#morphlevels = sorted(sdf['morphlevel'].unique())

#%%


rows = 'ypos'
cols = 'xpos'

row_vals = sorted(sdf[rows].unique())
col_vals = sorted(sdf[cols].unique())


#%%

# Compare against RETINO:
# -============================================================================

# sort cells:
retino_rois_fpath = glob.glob(os.path.join(fov_dir, 'retino*', 'retino_analysis', 'analysis*', 'visualization', 'rf_estimates', '2019*', '*.json'))[0]

with open(retino_rois_fpath, 'r') as f:
    retino_rois = json.load(f)
retino_top_rois = retino_rois['sorted_rois']

pl.figure()
all_rois = list(copy.copy(sorted_selective))
all_rois.extend(retino_top_rois)
all_rois = list(set(all_rois))

roi_matches = []
for r in all_rois:
    if r in sorted_selective and r in retino_top_rois:
        roi_matches.append([r, r])
    elif r in sorted_selective:
        roi_matches.append([0, r])
    elif r in retino_top_rois:
        roi_matches.append([r, 0])

roi_matches = np.array(roi_matches)
        
fig, ax = pl.subplots()
ax.scatter(roi_matches[:, 0], roi_matches[:, 1])
ax.set_xlabel('retino')
ax.set_ylabel('tiling')

roi_both = [r for r in all_rois if r in sorted_selective and r in retino_top_rois]
for ri, ridx in enumerate(roi_both):
    ax.text(roi_matches[ri, 0], roi_matches[ri, 1],'%i' % ridx, fontsize=12)

for r in all_rois:
    if r in sorted_selective and r in retino_top_rois:
        ax.scatter(r, r, 'p*')
    elif r in sorted_selective:
        ax.scatter(r, 0, 'r*')
    elif r in retino_top_rois:
        ax.scatter(0, r, 'b*')
        

#%%

# Plot zscored-traces of each "selective" ROI
# -============================================================================

#rows = 'size'
#cols = 'morphlevel'

plot_zscored = True
annotate = False
plot_average = True
plot_heatmap = False


figsize = (10,4)
axes_pad = 0.1
lw = 1

plot_type = 'heatmap' if plot_heatmap else 'traces'
average_str = 'average' if plot_average else 'trials'

subplot_aspect = 4 # (float(len(col_vals))/float(len(row_vals))) * 4.


# -----------------------------------------------------------------------------

config_trial_ixs = dict()
cix = 0
for si, row_val in enumerate(sorted(row_vals)):
    for mi, col_val in enumerate(col_vals):
        config_trial_ixs[cix] = {}
        cfg = sdf[(sdf[rows]==row_val) & (sdf[cols]==col_val)].index.tolist()[0]
        trial_ixs = sorted( list(set( [int(tr[5:])-1 for tr in labels[labels['config']==cfg]['trial']] )) )
        config_trial_ixs[cix]['config'] = cfg
        config_trial_ixs[cix]['trial_ixs'] = trial_ixs
        cix += 1


trace_type = 'zscored' if plot_zscored else 'raw'
curr_figdir = os.path.join(output_dir, 'roi_trials_by_cond_%s_%s_%s' % (trace_type, plot_type, average_str))
if not os.path.exists(curr_figdir):
    os.makedirs(curr_figdir)
print "Saving figures to:", curr_figdir


#%%
#rid = 137 #14
for rid in sorted_selective[0:10]:
    print rid
    roi_zscores = zscores[:, rid]
    if plot_zscored:
        roi_trace = zscored_traces[rid] #traces[:, rid]
        roi_metrics = zscores[:, rid]
        metric_name = 'zscore'
        value_name = 'zscore'
    else:
        roi_trace = raw_traces[rid]
        roi_metrics = snrs[:, rid]
        metric_name = 'snr'
        value_name = 'intensity'
        
    #ymin = roi_trace.min()
    #ymax = roi_trace.max()
        
    traces_by_config = dict((config, []) for config in labels['config'].unique())
    for k, g in labels.groupby(['config', 'trial']):
        traces_by_config[k[0]].append(roi_trace[g.index])
    for config in traces_by_config.keys():
        traces_by_config[config] = np.vstack(traces_by_config[config])
    
    
    fig = pl.figure(figsize=figsize) # (18,4))
    grid = AxesGrid(fig, 111, 
                    nrows_ncols=(len(row_vals), len(col_vals)),
                    axes_pad=axes_pad,
                    cbar_mode='single',
                    cbar_location='right',
                    cbar_pad=0.1)
    
    #aix = 0
    #zscores_by_cond_list = []
    for aix in sorted(config_trial_ixs.keys()): # Ordered by stim conditions
        #print aix
        
        ax = grid.axes_all[aix]
        cfg = config_trial_ixs[aix]['config']
        trial_ixs = config_trial_ixs[aix]['trial_ixs']
        
        curr_cond_traces = traces_by_config[cfg]

        if plot_heatmap:
            im = ax.imshow(curr_cond_traces, cmap='inferno')
        else:
            if plot_average:
                curr_cond_traces = curr_cond_traces.mean(axis=0)[stim_on_frame:stim_on_frame+nframes_on*2]
            ax.plot(curr_cond_traces, 'k', lw=lw)
        
        ax.set_aspect(subplot_aspect)

        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_yticklabels([])
        ax.set_xticklabels([])
        
        # get zscore values:
        curr_cond_metrics = roi_metrics[trial_ixs]
        if annotate:
            ax.set_title('%s %.2f (std %.2f)' % (metric_name, curr_cond_metrics.mean(), stats.sem(curr_cond_metrics)), fontsize=6)
            ax.set_ylabel('trial')
        
        ax.axvline(x=stim_on_frame, color='w', lw=0.5, alpha=0.5)
        ax.axvline(x=stim_on_frame+nframes_on, color='w', lw=0.5, alpha=0.5)
        
        if aix % len(col_vals) == 0:
            print aix
            ax.set_ylabel(int(sdf[rows][cfg]), rotation='horizontal', labelpad=20)
            
        sns.despine(left=True, bottom=True, ax=ax)
        #ax.set_ylim([ymin, ymax])
        
    fig.suptitle('roi %i' % int(rid+1))
    
    if plot_heatmap:
        cbar = ax.cax.colorbar(im)
        cbar = grid.cbar_axes[0].colorbar(im)
        cbar.ax.set_ylabel(value_name)
    
    figname = 'zscored_trials_roi%05d' % int(rid+1)
    label_figure(fig, data_identifier)
    pl.savefig(os.path.join(curr_figdir, '%s.png' % figname))
    
    #roi_zscores_by_cond = pd.DataFrame(zscores_by_cond_list).T
    #print roi_zscores_by_cond.head()

    pl.close()
    print figname


#%%
#
## Do any stats correlate nicely with mag of response?
responsive_test = 'RManova1'
vstats_fpath = glob.glob(os.path.join(sorted_dir,  'responsivity_%s*' % responsive_test, '*%s_results.json' % responsive_test ))[0]
with open(vstats_fpath, 'r') as f:
    vstats = json.load(f)
#
#stat_types = ['F', 'mse', 'eta', 'eta2_p']
#
#fig, axes = pl.subplots(1, len(stat_types))
#for aix, stat in enumerate(stat_types):
#    ax = axes[aix]
#    max_avg_zscore = np.array([avg_zscores_by_cond[rid].max() for rid in selective_rois])
#    vstat_val = [vstats[str(rid)][stat] for rid in selective_rois]
#    ax.scatter(max_avg_zscore, vstat_val)
#    
#
##%%
#rid = 14
#
#eta2s = []
#for rid in selective_rois:
#    aov_results_fpath = os.path.join(sorted_dir, 'responsivity', 'SPanova2_results', 'visual_anova_results_%s.txt' % rid)
#    with open(aov_results_fpath, 'rb') as f:
#        aov = f.read().strip()
#    
#    strt = aov.find('\nepoch * config') + 1
#    ed = aov[strt:].find('\n')
#    epoch_config_eta2 = float([s for s in aov[strt:strt+ed].split(' ') if s !=''][11])
#    eta2s.append(epoch_config_eta2)
#    
#pl.figure()
#pl.scatter(max_avg_zscore, eta2s)
#
#sort_by_eta2 = np.argsort(eta2s)[::-1]


#%%


# Plot "best" stimulus condition's traces for Top or Bottom N rois:
# -----------------------------------------------------------------------------
use_selective = True
plot_topN = True
    
nr = 10
nc = 6

if use_selective:
    roi_list = copy.copy(sorted_selective)
    sorter = 'selective'
else:
    roi_list = copy.copy(sorted_visual)
    sorter = 'visual'
    
if plot_topN:
    sort_order = 'top'
else:
    sort_order = 'bottom'
    
fig = pl.figure(figsize=(10,8))
grid = AxesGrid(fig, 111,
                nrows_ncols=(nr, nc),
                axes_pad=0.2,
                cbar_mode='single',
                cbar_location='right',
                cbar_pad=0.1)

aix = 0
nplots = min([nr*nc, len(roi_list)])

if not plot_topN:
    plot_order = roi_list[-nplots:]
else:
    plot_order = roi_list[0:nplots]
    
for rid in plot_order: #0:nplots]: #[0:nr*nc]:
    
    roi_zscores = zscores[:, rid]
    roi_trace = zscored_traces[rid] #[:, rid]

    traces_by_cond = dict((config, []) for config in labels['config'].unique())
    for k, g in labels.groupby(['config', 'trial']):
        traces_by_cond[k[0]].append(roi_trace[g.index])
    for config in traces_by_cond.keys():
        traces_by_cond[config] = np.vstack(traces_by_cond[config])

    best_cfg = 'config%03d' % int(avg_zscores_by_cond[rid].argmax()+1)
    curr_cond_traces = traces_by_cond[best_cfg]
    
    ax = grid.axes_all[aix]
    im = ax.imshow(curr_cond_traces, cmap='inferno')
    ax.set_aspect(2.5)
    ax.set_axis_off()
        
    ax.axvline(x=stim_on_frame, color='w', lw=0.5, alpha=0.5)
    ax.axvline(x=stim_on_frame+nframes_on, color='w', lw=0.5, alpha=0.5)
        
        
    ax.set_title('%i (%.2f)' % (rid, avg_zscores_by_cond[rid].max()), fontsize=6)
    aix += 1
    
cbar = ax.cax.colorbar(im)
cbar = grid.cbar_axes[0].colorbar(im)

for a in np.arange(aix, nr*nc):
    grid.axes_all[a].set_axis_off()
    
label_figure(fig, data_identifier)
figname = 'sorted_%s_best_cfg_zscored_trials_%s%i' % (sorter, sort_order, nplots)
pl.savefig(os.path.join(output_dir, '%s.png' % figname))
print figname


#%%
fig, ax = pl.subplots(figsize=(10,5)) #pl.figure(figsize=(10,5))

ax.plot(sorted_visual, np.array([avg_zscores_by_cond[rid].max() for rid in sorted_visual]), 'k.', markersize=10, label='visual', alpha=0.5) #, markersize=20, alpha=20)
ax.plot(sorted_selective, np.array([avg_zscores_by_cond[rid].max() for rid in sorted_selective]), 'r.', markersize=10, label='selective', alpha=0.5) #, markersize=20, alpha=20)
ax.set_ylabel('zscore')
ax.set_xlabel('roi')

ax.axhline(y=1, linestyle='--', color='k')

for rid in sorted_selective[0:10]:
    print rid
    ax.annotate('%i' % rid, (rid, float(avg_zscores_by_cond[rid].max())))

    
pl.legend()
label_figure(fig, data_identifier)

pl.savefig(os.path.join(output_dir, 'visual_selective_rois.png'))


#%%

#rows = 'yrot'
#cols = 'morphlevel'

curr_figdir = os.path.join(output_dir, 'selective_rois')
if not os.path.exists(curr_figdir):
    os.makedirs(curr_figdir)
print "Saving curr figures to: %s" % curr_figdir


min_snr =  2

# 1.  Plot raw traces and relationship between bas/stim periods w.r.t SNR
# -----------------------------------------------------------------------
#rid = sorted_selective[0]

for rid in sorted_selective[0:5]:
    roi_zscores = zscores[:, rid]
    roi_trace = raw_traces[rid] #[:, rid]
    
    # Get current ROI traces by config:
    traces_by_cond = dict((cfg, []) for cfg in labels['config'].unique())
    for k, g in labels.groupby(['config', 'trial']):
        traces_by_cond[k[0]].append(roi_trace[g.index])
    for cfg in traces_by_cond.keys():
        traces_by_cond[cfg] = np.vstack(traces_by_cond[cfg])
    
    
    # Pick condition with max/best zscore:
    sorted_configs_by_zscore = avg_zscores_by_cond[rid].argsort()[::-1].values
    
    best_cfg = 'config%03d' % int(sorted_configs_by_zscore[0]+1)
    
    # Get all trial indices of this config:
    ntrials = traces_by_cond[best_cfg].shape[0]
    best_cfg_trial_ixs = sorted(trials_by_cond[best_cfg])
    
    tmp_snrs = snrs[best_cfg_trial_ixs, rid]
    tmp_zscores = zscores[best_cfg_trial_ixs, rid]
    
    funky_vals = [i for i,v in enumerate(tmp_snrs) if abs(v) > 1000]
    normal_vals = np.array([i for i in np.arange(0, len(tmp_snrs)) if i not in funky_vals])
    curr_snrs = tmp_snrs[normal_vals]
    curr_zscores = tmp_zscores[normal_vals]
    
    #%
    fig, axes = pl.subplots(1,3, figsize=(25, 5)) #pl.figure()
    
    ax = axes[0]
    im = ax.imshow(traces_by_cond[best_cfg], cmap='inferno', aspect='auto')
    # Add color bar:
    divider = make_axes_locatable(ax)
    cax = divider.append_axes('right', size='1%', pad=0.1) 
    pl.colorbar(im, cax=cax, cmap='inferno')
    cax.yaxis.set_ticks_position('right')
    ax.set_title('raw traces (%s: %s %i, %s %i)' % (best_cfg, cols, sdf[cols][best_cfg], rows, sdf[rows][best_cfg]), fontsize=10)
    ax.set_ylabel('trial')
    ax.set_xlabel('frame')
    ax.set_xticks([]); ax.set_xticklabels([]);
    ax.axvline(x=stim_on_frame, color='w', lw=0.5)
    ax.axvline(x=stim_on_frame+nframes_on, color='w', lw=0.5)
    # Add color bar:
    divider = make_axes_locatable(ax)
    cax = divider.append_axes('right', size='5%', pad=0.05) 
    pl.colorbar(im, cax=cax, cmap='inferno')
    cax.yaxis.set_ticks_position('right')
        
    ax = axes[1]
    ax.plot(curr_zscores, curr_snrs, 'b.', markersize=20, alpha=0.5, label='best')
    ax.set_ylabel('snr')
    ax.set_xlabel('zscore')
    ax.set_title('zscores vs snr (best cfg)')
    for tid in np.arange(0, curr_snrs.shape[0]):
        ax.annotate('%i' % tid, (curr_zscores[tid], curr_snrs[tid]), fontsize=6)
    ax.set_ylim([min([-2, abs(curr_snrs.min()-1)]), curr_snrs.max()+1])
    ax.set_xlim([min([-2, abs(curr_zscores.min()-1)]), curr_zscores.max()+1])
    # Also plot "worst"?
    worst_cfg = 'config%03d' % int(sorted_configs_by_zscore[-1]+1)
    ax.plot(zscores[trials_by_cond[worst_cfg], rid], snrs[trials_by_cond[worst_cfg], rid],\
            'r.', markersize=20, alpha=0.5, label='worst')
    ax.legend()
    ax.axhline(y=min_snr, linestyle='--', color='k')
    
    
    
    # Plot distN of all sizes @ best morph, all morphs @ best size:
    snr_df = pd.concat([pd.Series(snrs[trial_ixs, rid], name=k) for k, trial_ixs in sorted(trials_by_cond.items(), key=lambda x: x[0])], axis=1)
    snr_df2 = snr_df.melt(var_name='configs', value_name='snr')
    snr_df2[cols] = pd.Series(sdf[cols][cfg] for cfg in snr_df2['configs'])
    snr_df2[rows] = pd.Series(sdf[rows][cfg] for cfg in snr_df2['configs'])
    ax = axes[2]
    ax.clear()
    g = sns.stripplot(x=cols, y='snr', hue=rows, data=snr_df2, ax=ax,
                      jitter=True, dodge=True, alpha=0.5, size=5, palette=sns.cubehelix_palette(len(row_vals))) #'GnBu_d')
    ax.set_ylim([-10, min([snr_df.max().max(), 100])])
    sns.despine(trim=True,offset=4, ax=ax)
    
    fig.suptitle('roi #%i' % int(rid+1))
    
    pl.subplots_adjust(top=0.8)
    
    figname = 'roi%05d_%s_rawtraces_snr' % (int(rid+1), cfg)
    label_figure(fig, data_identifier)
    pl.savefig(os.path.join(curr_figdir, '%s.png' % figname))
    
    pl.close()

#%%


#g = sns.FacetGrid(snr_df2, col='morphlevel')
#g.map(sns.stripplot, "size", "snr", alpha=0.5, color='k', jitter=True, size=5)
#sns.despine(trim=True,offset=4)
#   
#g = sns.FacetGrid(snr_df2, col='size')
#g.map(sns.stripplot, "morphlevel", "snr", alpha=0.5, color='k', jitter=True, size=5)
#sns.despine(trim=True,offset=4) 
#
#
##%%
#
#
## Is SNR a better measure?
#
#nr = 5
#nc = 8
#fig, axes = pl.subplots(nr, nc, figsize=(18,9), sharex=True, sharey=True)
#ai = 0
#n_subplots = min([nr*nc, len(sorted_selective)])
#for rid in sorted_selective[0:n_subplots]:
#    ax  = axes.flat[ai]
#    ax.scatter(zscores[:, rid], snrs[:, rid], alpha=0.5, s=5)
#    ax.set_title(rid)
#    ai += 1
#    
#pl.subplots_adjust(hspace=0.5, wspace=0.5)
#
#avg_snrs = []
##avg_snrs_by_cond = [snrs.iloc[trial_ixs].mean(axis=0) for cfg, trial_ixs in trials_by_cond.items()]
#for cfg, trial_ixs in sorted(trials_by_cond.items(), key=lambda x: x[0]):
#    avg_snrs.append(pd.Series(snrs[trial_ixs, :].mean(axis=0)))
#avg_snrs_by_cond = pd.concat(avg_snrs, axis=1).T
#    
#
#max_zscores_by_roi = [avg_zscores_by_cond[rid].max() for rid in sorted_selective]
#max_snrs_by_roi = [avg_snrs_by_cond[rid].max() for rid in sorted_selective]
#pl.figure()
#pl.scatter(max_zscores_by_roi, max_snrs_by_roi)

#%%


 # make conditions = columns (for corr()) #avg_zscores_by_cond[sorted_selective]

def plot_corrs_by_cond(conds_by_rois, grid_axis='size', grid_values=[], \
                       plot_axis='morphlevel', plot_values=[], title=None,\
                       corr_method='pearson', rdm=False, cmap='coolwarm'):
    
    if rdm: # == 'rdm':
        vmin=0; vmax=2; 
    else:
        vmin=-1; vmax=1; 
    
    fig, axes = pl.subplots(1, len(grid_values), figsize=(len(grid_values)*2,2)) #pl.figure()
    for ci, cv in enumerate(sorted(grid_values)):
        curr_cixs = [int(cfg[6:])-1 for cfg in sdf[sdf[grid_axis]==cv].index.tolist()]
        corr_cdim = conds_by_rois[curr_cixs].corr(method=corr_method)
        if rdm:
            corr_cdim = 1 - corr_cdim
        ax = axes[ci]
        if ci == 0:
            ax.set_ylabel(plot_axis)
            ax.set_yticks(np.arange(0, len(plot_values)))
            ytick_labels = sorted(plot_values)
            ax.set_yticklabels(ytick_labels, rotation=0, fontsize=6)
            ax.set_xticks([])
            ax.set_ylabel(plot_axis)
        else:
            ax.set_xticks([])
            ax.set_yticks([])
        im = ax.imshow(corr_cdim, cmap=cmap, vmin=vmin, vmax=vmax, aspect='equal')
        ax.set_title('%i' % cv, fontsize=6)
    
    if title is None:
        title = '%s corrs by %s' % (plot_axis, grid_axis)
    fig.suptitle(title, fontsize=12)
    fig.subplots_adjust(right=0.78, top=0.77, wspace=0.2)
    cbar_ax = fig.add_axes([0.8, 0.2, 0.01, 0.5]) # put colorbar at desire position
    fig.colorbar(im, cax=cbar_ax)
    
    return fig

#%%

import matplotlib as mpl
import numpy as np
import sys
def make_cmap(colors, position=None, bit=False):
    '''
    make_cmap takes a list of tuples which contain RGB values. The RGB
    values may either be in 8-bit [0 to 255] (in which bit must be set to
    True when called) or arithmetic [0 to 1] (default). make_cmap returns
    a cmap with equally spaced colors.
    Arrange your tuples so that the first color is the lowest value for the
    colorbar and the last is the highest.
    position contains values from 0 to 1 to dictate the location of each color.
    '''

    bit_rgb = np.linspace(0,1,256)
    if position == None:
        position = np.linspace(0,1,len(colors))
    else:
        if len(position) != len(colors):
            sys.exit("position length must be the same as colors")
        elif position[0] != 0 or position[-1] != 1:
            sys.exit("position must start with 0 and end with 1")
    if bit:
        for i in range(len(colors)):
            colors[i] = (bit_rgb[colors[i][0]],
                         bit_rgb[colors[i][1]],
                         bit_rgb[colors[i][2]])
    cdict = {'red':[], 'green':[], 'blue':[]}
    for pos, color in zip(position, colors):
        cdict['red'].append((pos, color[0], color[0]))
        cdict['green'].append((pos, color[1], color[1]))
        cdict['blue'].append((pos, color[2], color[2]))

    cmap = mpl.colors.LinearSegmentedColormap('my_colormap',cdict,256)
    return cmap

#%%
dubrovnik_colors = [(0, 0, 1),
                   (0, 1, 1),
                   (.197, .408, .408),
                   (.402, .402, .204),
                   (1, 1, 0),
                   (1, 0, 0)
                   ]

dubrovnik = make_cmap(dubrovnik_colors, bit=False)
dubrovnik_positions = [p/255. for p in [0, 83, 127, 128, 172, 255]]

#%

skalafell_colors = [(1, 0, 1),
                   (1, 0.9921, 1),
                   (0.9921, 1, 0.9921),
                   (0, 1, 0)
                   ]
skalafell_positions = [p/255. for p in [0, 127, 128, 255]]
skalafell = make_cmap(skalafell_colors, bit=False, position=skalafell_positions)

#%
nanticoke_colors = [(0, 1, 1),
                   (0, 0.2, 1),
                   (0, 0, 0),
                   (1, 0.1, 0),
                   (1, 0.9, 0)
                   ]
nanticoke_positions = [p/255. for p in [0, 51, 102, 163, 255]]
nanticoke = make_cmap(nanticoke_colors, bit=False, position=nanticoke_positions)




### Use your colormap
pl.pcolor(np.random.rand(25,50), cmap=nanticoke)
pl.colorbar()
         
#%%
#from matplotlib.colors import ListedColormap
#cmap = ListedColormap( sns.diverging_palette(10, 220, sep=80).as_hex())


subsets = ['visual', 'selective']

subtract_GM = True
corr_method = 'pearson' #'spearman' #'pearson'
rdm = True

cmap = 'PRGn'
#if rdm:
#    cmap = sns.diverging_palette(280, 145, s=85, l=25, as_cmap=True) #, reverse=True)
#else:
#    cmap = sns.diverging_palette(145, 280, s=85, l=25, as_cmap=True)

#cmap = sns.diverging_palette(10, 220, sep=80) # 'PRGn' #dubrovnik #nanticoke #skalafell #dubrovnik #PRGn'

fig_subdir = '%s_%s_corrs_GM' % (cols, rows) if subtract_GM else '%s_%s_corrs' % (cols, rows)

if segment:
    curr_figdir = os.path.join(traceid_dir, 'figures', 'population', fig_subdir, visual_area)
else:
    curr_figdir = os.path.join(traceid_dir, 'figures', 'population', fig_subdir)
if not os.path.exists(curr_figdir):
    os.makedirs(curr_figdir)
print "Saving plots to: %s" % curr_figdir

#%
if rdm:
    rdm_str = 'rdm'
else:
    rdm_str = 'corr'

for subset in subsets:
    #%
    if subset == 'visual':
        conds_by_rois = avg_zscores_by_cond[sorted_visual].T #.T.corr()
    elif subset == 'selective':
        conds_by_rois = avg_zscores_by_cond[sorted_selective].T #.T.corr()
    else:
        conds_by_rois = avg_zscores_by_cond[all_rois].T
    
    GM = conds_by_rois.mean().mean()
    
    if subtract_GM:
        conds_by_rois = conds_by_rois - GM
        
    print conds_by_rois.shape
    #%
    # Plot ALL correlations:
    # ----------------------
    fig, ax = pl.subplots() #pl.figure()
    if rdm:
        vmin=0; vmax=2; 
    else:
        vmin=-1; vmax=1;
        
    im = ax.imshow(conds_by_rois.corr(method=corr_method), cmap=cmap, vmin=vmin, vmax=vmax, aspect='equal')
    ax.set_title('%s corrs - all condNs (%s)' % (corr_method, subset))
    divider = make_axes_locatable(ax)
    cax = divider.append_axes('right', size='3%', pad=0.1) 
    pl.colorbar(im, cax=cax, cmap=cmap)
    cax.yaxis.set_ticks_position('right')
    label_figure(fig, data_identifier)
    figname = 'allcond_%s_%s_%s' % (corr_method, rdm_str, subset)
    pl.savefig(os.path.join(curr_figdir, '%s.png' % figname))
    print figname
    
    
    col_vals = sorted(sdf[cols].unique())
    row_vals = sorted(sdf[rows].unique())
    
    # Plot morph correlations for each size:
    # --------------------------------------
    grid_axis = rows; grid_values = copy.copy(row_vals);
    plot_axis = cols; plot_values = copy.copy(col_vals);
    fig = plot_corrs_by_cond(conds_by_rois, grid_axis=grid_axis, grid_values=grid_values,\
                             plot_axis=plot_axis, plot_values=plot_values,\
                             corr_method=corr_method, rdm=rdm, cmap=cmap,\
                             title='%s corrs (%s) by %s (%s)' % (plot_axis, corr_method, grid_axis, subset))
    
    label_figure(fig, data_identifier)
    figname = '%s_%s_%s_by_%s_%s' % (plot_axis, corr_method, rdm_str, grid_axis, subset)
    pl.savefig(os.path.join(curr_figdir, '%s.png' % figname))
    print figname
    
    # Plot size correlations for each morph:
    # --------------------------------------
    grid_axis = cols; grid_values = copy.copy(col_vals);
    plot_axis = rows; plot_values = copy.copy(row_vals);
    fig = plot_corrs_by_cond(conds_by_rois, grid_axis=grid_axis, grid_values=grid_values,\
                             plot_axis=plot_axis, plot_values=plot_values,\
                             corr_method=corr_method, rdm=rdm, cmap=cmap,\
                             title='%s corrs (%s) by %s (%s)' % (plot_axis, corr_method, grid_axis, subset))
    label_figure(fig, data_identifier)
    figname = '%s_%s_%s_by_%s_%s' % (plot_axis, corr_method, rdm_str, grid_axis, subset)
    pl.savefig(os.path.join(curr_figdir, '%s.png' % figname))
    print figname

#%%
import seaborn as sns


fig, ax = pl.subplots()
for cv in sizes:
    curr_cixs = np.array([int(cfg[6:])-1 for cfg in sdf[sdf['size']==cv].index.tolist()])
    curr_sz_vals = avg_zscores_by_cond[sorted_visual].iloc[curr_cixs, :]
    sns.distplot(curr_sz_vals.values.ravel(), ax=ax, label=cv, hist=False, rug=False)
    





