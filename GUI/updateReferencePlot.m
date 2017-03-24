function [handles, D] = updateReferencePlot(handles, D, newReference, showRois)

avgimg = getCurrentSliceImage(handles, D);      % Get avg image for selected slice and file.

if newReference==1
    fprintf('Loading data for selected slice...\n');
    
    %   avgimg = getCurrentSliceImage(handles, D);
    maskcell = getCurrentSliceMasks(handles,D);        % Get masks for currently selected slice. % NOTE:  Masks created could go with different file.
    setappdata(handles.roigui, 'maskcell', maskcell);
    
    setRoiMax(handles, maskcell);                      % Set Max values for ROI entries.

    [RGBimg, masksRGBimg] = createRGBimg(avgimg, maskcell);         % Create RGB image for average slice and masks.
    
    D.RGBimg = RGBimg;
    D.masksRGBimg = masksRGBimg;
    D.avgimg = avgimg;
    
    fprintf('Done!\n');
end

handles.currSlice.UserData.sliceValue = handles.currSlice.Value;
handles.runMenu.UserData.runValue = handles.runMenu.Value;

selectedROI = str2double(handles.currRoi.String);
maskcell = getappdata(handles.roigui,'maskcell');
D.masksRGBimg(:,:,1) = D.masksRGBimg(:,:,1).*0;
D.RGBimg(:,:,1) = D.RGBimg(:,:,1).*0;
D.RGBimg(:,:,3) = D.RGBimg(:,:,3).*0;
    
if selectedROI>0
    D.masksRGBimg(:,:,1) = D.masksRGBimg(:,:,1)+0.7*full(maskcell{selectedROI});
    D.RGBimg(:,:,1) = D.RGBimg(:,:,1)+0.7*full(maskcell{selectedROI});
    D.RGBimg(:,:,3) = D.RGBimg(:,:,3)+0.7*full(maskcell{selectedROI});
end

axes(handles.ax1);
% if showRois==1
%     handles.avgimg = imagesc2(D.masksRGBimg);
% else
%     handles.avgimg = imagesc2(D.RGBimg);
% end

switch D.maskType
    case 'nmf'
        handles.avgimg = plot_contours(maskcell,scalefov(D.masksRGBimg),D.maskInfo.nmfoptions,1);
    otherwise
        if showRois==1
            if newReference==1
                handles.avgimg = imagesc2(scalefov(D.masksRGBimg)); %, handles.ax1); %, 'Parent',handles.ax1, 'PickableParts','none', 'HitTest','off');%imagesc(D.masksRGBimg);
            else
                handles.avgimg = findobj(handles.ax1, 'Type', 'image', '-depth', 1);
                handles.avgimg.CData = D.masksRGBimg; %imshow(D.masksRGBimg);
            end
        else
            if newReference==1
                handles.avgimg = imagesc2(scalefov(D.RGBimg)); %, 'Parent',handles.ax1, 'PickableParts','none', 'HitTest','off');%imagesc(D.masksRGBimg); %imshow(D.masksRGBimg);
            else
                handles.avgimg.CData = D.RGBimg; % = imshow(D.RGBimg);
            end
        end
end

handles.avgimg.HitTest = 'on';
handles.avgimg.PickableParts = 'visible';

%handles.avgimg.Parent.HitTest = 'off';

% handles.avgimg.Parent.Units = 'pixel';
% 
% S.ax = handles.avgimg.Parent; %handles.avgimg.Parent;
% S.axp = S.ax.Position;
% S.xlm = S.ax.XLim;
% S.ylm = S.ax.YLim;
% S.dfx = diff(S.xlm);
% S.dfy = diff(S.ylm);

%set(S.ax,'ax1_ButtonDownFcn',{@fh_wbmfcn,S}) % Set the motion detector.

end