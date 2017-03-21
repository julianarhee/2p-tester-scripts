function [trace_y, DC_y] = subtractRollingMean(currTrace, winsz)
    % if cutEnd==1
    %     tmp0 = currTrace(1:crop);
    % else
    ind = 1:length(currTrace);
    ix = ~isnan(currTrace);
    if sum(ix) ~= length(currTrace)
        tmp0 = interp1(ind(ix),currTrace(ix),ind,'linear');
    else
        tmp0 = currTrace;
    end
    %tmp0 = currTrace;
    % end
    tmp1 = padarray(tmp0,[0 winsz],tmp0(1),'pre');
    tmp1 = padarray(tmp1,[0 winsz],tmp1(end),'post');
    rollingAvg=nanconv(tmp1,fspecial('average',[1 winsz]),'same');%average
    rollingAvg=rollingAvg(winsz+1:end-winsz);
    trace_y = tmp0 - rollingAvg;
    
    DC_y = mean(tmp0);
    
end