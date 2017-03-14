function M = get_mw_info(mwPath, nTiffs)

fileNames = dir(fullfile(mwPath, '*.mat'));
if isempty(fileNames)
    
    fprintf('Failed to find corresponding MW-parsed .mat file for current acquisition %s.\n', mwPath);
    
    if exist(mwPath,'dir')
        fprintf('Found MW path at %s, but .mwk file is not yet parsed.\n', mwPath);
    end
    mw2si = 'unknown';
else
    fileNames = {fileNames(:).name}';
    fprintf('Found %i MW files and %i TIFFs.\n', length(fileNames), nTiffs);
    pymatName = fileNames{1};
    pymat = load(fullfile(mwPath, pymatName));
    nRuns = length(double(pymat.triggers)); % Just check length of a var to see how many "runs" MW-parsing detected.
   
    fprintf('---------------------------------------------------------\n');
    if length(fileNames) == nTiffs        
        fprintf('Looks like indie runs.\n');
        mw2si = 'indie';
        MWfidx = 1;
    elseif length(fileNames)==1
        fprintf('Multiple SI runs found in current MW file %s.\n', pymatName);
        fprintf('MW detected %i runs, and there are %i TIFFs.\n', nRuns, nTiffs);
        fprintf('---------------------------------------------------------\n');
        if nRuns==nTiffs % Likely, discarded/ignored TIFF files for given MW session
            MWfidx = 1;
            mw2si = 'multi';
            fprintf('Found correct # of runs in MW session to match # TIFFs.\n');
            fprintf('Setting mw-fix to 1.\n');
        elseif nRuns > nTiffs            
            MWfidx = (nRuns - nTiffs) + 1; % EX: TIFF file1 is really corresponding to MW 'run' 4 if ignoring first 3 TIFF files.
            mw2si = 'multi';
            fprintf('Looks like %i TIFF files should be ignored.\n', (nRuns-nTiffs));
            fprintf('Setting MW file start index to %i.\n', MWfidx);
        else
            fprintf('**Warning** There are fewer MW runs than TIFFs. Is MW file parsed correctly?\n');
            mw2si = 'unknown';
        end
    else               
        fprintf('Mismatch in num of MW files (%i .mwk found) and TIFF files (%i .tif found).\n', length(fileNames), nTiffs);
        mw2si = 'unknown';        
    end
end

switch mw2si
    case 'indie' % Each SI file goes with one MW/ARD file
        % do stuff
    case 'multi'
        % do other stuff
        pymatName = fileNames{1}; % There should only be 1 mwk file for multiple TIFFs (experiment reps).
        pymat = load(fullfile(mwPath, pymatName));
        %runNames = cellstr(pymat.conditions);
        if strcmp(pymat.stimtype, 'bar')
            % sthmight be off here, edited..
            runNames = cellstr(pymat.runs);
            condTypes = cellstr(pymat.condtypes);
        elseif strcmp(pymat.stimtype, 'grating')
            condTypes = cellstr(pymat.condtypes);
        elseif strcmp(pymat.stimtype, 'image')
            runNames = cellstr(pymat.runs);
            condTypes = cellstr(pymat.condtypes);
        else
            fprintf('No stimype detected in MW file...\n');
        end

    otherwise
        % fix stuff.
end


M.mwPath = mwPath;
M.runNames = runNames;
M.fileNames = fileNames;
M.mw2si = mw2si;
M.MWfidx = MWfidx;
M.nRuns = nRuns;
M.nTiffs = nTiffs;
M.condTypes = condTypes;
M.stimType = pymat.stimtype;
M.pymat = pymat;
end