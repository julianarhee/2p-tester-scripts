function post_mc_cleanup(mcparams, split_channels)

tmp_acq_obj = load(mcparams.acq_object_path);
acq_obj = tmp_acq_obj.(mcparams.acquisition_name);

% Sort Parsed files into separate directories if needed:
tmpchannels = dir(mcparams.output_dir);
tmpchannels = tmpchannels(arrayfun(@(x) ~strcmp(x.name(1),'.'), tmpchannels));
tmpchannels = tmpchannels([tmpchannels.isdir]);
tmpchannels = {tmpchannels(:).name}';
%if length(dir(fullfile(D.sourceDir, D.tiffSource, tmpchannels{1}))) > length(tmpchannels)+2
if isempty(tmpchannels) %|| any(strfind(D.tiffSource, 'Parsed'))
    sort_deinterleaved_tiffs(mcparams);
end
        
% Re-interleave TIFF slices:
% split_channels = false;
reinterleave_tiffs(acq_obj, split_channels); %, info);


end