function updateActivityMap(handles, D)

[tmpP, tmpN,~]=fileparts(D.outputDir);
selectedSliceIdx = handles.currSlice.Value; %str2double(handles.currSlice.String);
selectedSlice = D.slices(selectedSliceIdx);
selectedFile = handles.runMenu.Value;

meta = getappdata(handles.roigui, 'meta');
currRunName = meta.file(selectedFile).mw.runName;

mapStructName = sprintf('maps_Slice%02d', selectedSlice); 
mapStruct = load(fullfile(D.guiPath, tmpN, mapStructName));
mapTypes = fieldnames(mapStruct.file(selectedFile));

selectedMapIdx = handles.mapMenu.Value;
selectedMapType = mapTypes{selectedMapIdx};
displayMap = mapStruct.file(selectedFile).(selectedMapType);
magMap = mapStruct.file(selectedFile).magnitude;

currThresh = str2double(handles.threshold.String);
thresholdMap = threshold_map(displayMap, magMap, currThresh);

%avgimg = getCurrentSliceImage(handles, D);
fov = repmat(mat2gray(D.avgimg), [1, 1, 3]);

switch selectedMapType
    
    case 'phase'
        thresholdMap = threshold_map(displayMap, magMap, currThresh);
        axes(handles.ax2);  
        handles.map = imagesc(fov);
        hold on;
        handles.map = imagesc2(thresholdMap);
        colormap(handles.ax2, hsv);
        caxis([min(displayMap(:)), max(displayMap(:))]);
        colorbar off;
        
    case 'phasemax'
        thresholdMap = threshold_map(displayMap, magMap, currThresh);
        axes(handles.ax2);  
        handles.map = imagesc(fov);
        hold on;
        handles.map = imagesc2(thresholdMap);
        colormap(handles.ax2, hsv);
        caxis([min(displayMap(:)), max(displayMap(:))]);
        colorbar off;

        
    otherwise
        % 'ratio' 
        % 'magnitude'
        % 'maxDf'
        axes(handles.ax2);  
        handles.map = imagesc2(displayMap);
        colormap(handles.ax2, hot);
        caxis([min(displayMap(:)), max(displayMap(:))])
        colorbar();

    
end
refPos = handles.ax1.Position;
ax2Pos = handles.ax2.Position;
handles.ax2.Position(3:4) = [refPos(3:4)];
title(currRunName);
%colorbar();
%
end