import time
import sys
import almath
import Image, ImageDraw
from naoqi import ALProxy
import matplotlib.pyplot as plt
import numpy as np
import cv2
import cPickle
import pymorph

########################################################################################################################

def fcnThresh(image, function):
    width, height = image.size
    imagedecomp=image.load()
    imnew=Image.new('1',(width,height))
    imnewraw=imnew.load()
    immode=image.mode
    if 'RGB' in immode:
        for x in range(0,width):
            for y in range(0,height):
                imnewraw[x,y]= function(imagedecomp[x,y][0],imagedecomp[x,y][1],imagedecomp[x,y][2])==True
    else:
        for x in range(0,width):
            for y in range(0,height):
                imnewraw[x,y]= function(imagedecomp[x,y])==True
    return imnew

########################################################################################################################

def medfilt (x, k):
    """Apply a length-k median filter to a 1D array x.
    Boundaries are extended by repeating endpoints.
    """
    assert k % 2 == 1, "Median filter length must be odd."
    assert x.ndim == 1, "Input must be one-dimensional."
    k2 = (k - 1) // 2
    y = np.zeros ((len (x), k), dtype=x.dtype)
    y[:,k2] = x
    for i in range (k2):
        j = k2 - i
        y[j:,i] = x[:-j]
        y[:j,i] = x[0]
        y[:-j,-(i+1)] = x[j:]
        y[-j:,-(i+1)] = x[-1]
    return np.median (y, axis=1)

########################################################################################################################


def hist_thresh_new(image, seed_color, sat_cutoff, val_cutoff, window_size, bins):
    # image = cv2.medianBlur(image, 9)
    # image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    #image[:, :, 0] *= 255.0/180.0

    hue_hist, nums = np.histogram(image[:, :, 0], bins, (0, 255))

    hue_hist_filtered = medfilt(np.array(hue_hist), 3)
    # for i in range(len(hue_hist_filtered)):
    #     print(hue_hist_filtered[i])

    width = 0.7 * (nums[1] - nums[0])
    center = (nums[:-1] + nums[1:]) / 2
    plt.bar(center, hue_hist_filtered, align='center', width=width)
    plt.ion()
    plt.show()
    plt.pause(1)
    plt.clf()
    # plt.bar(center, hue_hist_filtered, align='center', width=width)
    # plt.ion()
    # plt.show()
    # plt.pause(1)
    # sat_mask = image[:, :, 1] > 0 #sat_cutoff
    # val_mask = image[:, :, 2] > 0 #val_cutoff
    #
    # cv2.imshow("sat_mask", sat_mask*255)
    # cv2.imshow("val_mask", val_mask*255)
    # cv2.waitKey(1)

    # find local minimums in the histogram
    local_minimums = []
    for i in range(window_size):
        window = np.concatenate((hue_hist_filtered[(bins-1-window_size+i):bins], hue_hist_filtered[0:(i+window_size+1)]))
        if hue_hist_filtered[i] == min(window):
            local_minimums += [i]
    for i in range(window_size, bins-window_size-1):
        window = hue_hist_filtered[(i-window_size):(i+window_size+1)]
        if hue_hist_filtered[i] == min(window):
            local_minimums += [i]
    for i in range(bins-window_size, bins-1):
        window = np.concatenate((hue_hist_filtered[(i-window_size):(bins)], hue_hist_filtered[0:i+window_size-bins+1]))
        if hue_hist_filtered[i] == min(window):
            local_minimums += [i]

    # did not find any minimums --> error!
    if len(local_minimums) <= 1:
        print('Something went wrong in calculating local minimums')
        return None

    # remove local minimums next to each other
    indices_to_delete = []
    for i in range(len(local_minimums)-1):
        if local_minimums[i+1] == local_minimums[i]+1:
            if local_minimums[(i+2) % len(local_minimums)] == local_minimums[i+1]+1:
                indices_to_delete += [i+1]
    if indices_to_delete:
        for index in reversed(indices_to_delete):
            del local_minimums[index]

    print('Local minimums %s' % local_minimums)
    # print('Local minimums: %s' % local_minimums)
    modality_means = []
    px_num = []
    mean_accumulator = 0
    num_el = 0

    # calculate mean values for each mode
    # mode is between two local minimums in the histogram
    # modality mean is calculated as weighted average of values in mode
    for i in range(0, len(local_minimums)-1):
        for j in range(local_minimums[i], local_minimums[i+1]):
            mean_accumulator += j*hue_hist_filtered[j]
            num_el += hue_hist_filtered[j]
            # print('num_el in the loop %s' % num_el)
            # print('hist[i] %s' % hue_hist_filtered[j])
        px_num += [num_el]
        if num_el == 0:
            modality_means += [local_minimums[i]/2.0+local_minimums[i+1]/2.0]
        else:
            modality_means += [1.0*mean_accumulator/num_el]
        mean_accumulator = 0
        # print('num_el %s' % num_el)
        num_el = 0
    print('px_num _ 1 %s' % px_num)
    # hue values are circular, wrap around to calculate mean between last and first minimum
    for j in range(local_minimums[len(local_minimums)-1], bins)+range(0, local_minimums[0]):
        if j > bins/2.0:
            mean_accumulator += (j-bins)*hue_hist_filtered[j]
        else:
            mean_accumulator += j*hue_hist_filtered[j]
        num_el += hue_hist_filtered[j]
    if num_el == 0:
        t_means = local_minimums[0]/2.0+bins/2.0+local_minimums[-1]/2.0
    else:
        t_means = 1.0*mean_accumulator/num_el
    px_num += [num_el]
    if t_means < 0:
        t_means += bins
    modality_means += [t_means]

    print('Modality means: %s' % modality_means)
    print('px_num: %s' % px_num)

    bin_val = bins/180.0
    hist_seed = round(seed_color*bin_val)
    print('seed_color %s' % seed_color)
    print('bin_val %s' % bin_val)
    print('hist_seed %s' % hist_seed)
    best = -1
    closest = bins+100

    for i in range(0, len(modality_means)):
        # TODO: check what this number 10000 does
        # print('hist_seed-modality_means[i] = %s' % (hist_seed-modality_means[i]))
        # print('px_num[i] = %s' % px_num[i])
        if closest > abs(hist_seed-modality_means[i]) and px_num[i] > 500:
            best = i
            closest = abs(hist_seed-modality_means[i])

    print('best = %s' % best)
    print('closest = %s' % closest)
    if best == len(modality_means)-1:
        hue_mask = np.logical_or(image[:, :, 0] >= local_minimums[len(local_minimums)-1]/bin_val, image[:, :, 0] <= local_minimums[0]/bin_val)
    else:
        hue_mask = np.logical_and(image[:, :, 0] >= local_minimums[best]/bin_val, image[:, :, 0] <= local_minimums[best+1]/bin_val)
    sat_mask = image[:, :, 1] > sat_cutoff
    val_mask = image[:, :, 2] > val_cutoff

    res_img = np.logical_and(hue_mask, val_mask)
    res_img = np.logical_and(res_img, sat_mask)
    res_img = cv2.dilate(res_img*1.0, np.ones((10, 10)))
    res_img = cv2.erode(res_img*1.0, np.ones((10, 10)))

    return cv2.convertScaleAbs(res_img*255)


def histThresh(image, seedcolor, diagnostic):
    image = cv2.medianBlur(image, 9)
    image=cv2.cvtColor(image,cv2.cv.CV_RGB2HSV)
    # image[:,:,0]*=255.0/180.0 # not work!!!
    width = np.size(image,1)
    height = np.size(image,0)
    saturationCutoff=255*0.3
    valueCutoff=255*0.1
    windowsize=15

    dest=np.zeros((width, height))
    sMask=np.zeros((width, height))
    vMask=np.zeros((width, height))
    hMask=np.zeros((width, height))

    bins = 128
    valperbin = bins/255.0
    hueHist, nums=np.histogram(image[:,:,0],bins,(0,255))
    sMask=image[:,:,1]>saturationCutoff
    vMask=image[:,:,2]>valueCutoff

    #cv2.imwrite('satmask.png',sMask*255.0)
    #cv2.imwrite('valmask.png',vMask*255.0)
    #print("Saved ----------------- SAVED ---------------- SAVED !!!!! %%%%%")

    hueHistOrig=hueHist
    hueHist2=medfilt(np.array(hueHist),3)

    hueHist=hueHist2

    localMinima = []
    for i in range(0,windowsize):
        window = np.concatenate((hueHist[(bins-1-windowsize+i):bins],hueHist[0:(i+windowsize+1)]))
        if hueHist[i] == min(window):
            localMinima += [i]

    for i in range(windowsize, bins-windowsize-1):
        window = hueHist[(i-windowsize):(i+windowsize+1)]
        if hueHist[i] == min(window):
            localMinima += [i]

    for i in range(bins-windowsize, bins-1):
        window = np.concatenate((hueHist[(i-windowsize):(bins)],hueHist[0:i+windowsize-bins+1]))
        if hueHist[i] == min(window):
            localMinima += [i]

    if len(localMinima)==1:
        return cv2.convertScaleAbs(np.zeros((width, height)))

    modalityMeans = []
    nPx=[]
    meanAccumulator = 0
    numel = 0
    for i in range(0, len(localMinima)-1):
        for j in range(localMinima[i], localMinima[i+1]):
            meanAccumulator+=j*hueHist[j]
            numel+=hueHist[j]
        nPx+=[numel]
        #print("NUMEL NUMEL NUMEL %s" % numel)
        modalityMeans+=[1.0*meanAccumulator/(numel)]
        meanAccumulator = 0
        numel = 0

    for j in range(localMinima[len(localMinima)-1], bins)+range(0, localMinima[0]):
        if (j>bins/2.0):
            meanAccumulator+=(j-bins)*hueHist[j]
        else:
            meanAccumulator+=j*hueHist[j]
        numel+=hueHist[j]
    tmeans=1.0*meanAccumulator/(numel)
    nPx+=[numel]
    if (tmeans<0):
        tmeans = bins+tmeans
    modalityMeans+=[tmeans]

    histSeed=round(255.0*seedcolor*valperbin)


    best = -1
    closest = bins+100
    for i in range(0,len(modalityMeans)):
        if closest>abs(histSeed-modalityMeans[i]) and nPx[i]>10000:
            best = i
            closest = abs(histSeed-modalityMeans[i])

    if (best == len(modalityMeans)-1):
        hMask=np.logical_or(image[:,:,0]>=localMinima[len(localMinima)-1]/valperbin,image[:,:,0]<=localMinima[0]/valperbin)
    else:
        hMask=np.logical_and(image[:,:,0]>=localMinima[best]/valperbin,image[:,:,0]<=localMinima[best+1]/valperbin)

    dest=np.logical_and(hMask,vMask)
    dest=np.logical_and(dest,sMask)

    modalityMeans = np.rint(modalityMeans)

    if diagnostic:
        print modalityMeans
        print localMinima
        print nPx
        print best

        num = 10000
        diagArray = hueHist.copy()

        for i in range(0,bins):
            if i in modalityMeans:
                diagArray[i]=num+10000
            else:
                diagArray[i]=num

            if i in localMinima:
                if i == localMinima[best]:
                    num = 20000
                else:
                    if num ==10000:
                        num = 0
                    else:
                        num = 10000

        #plt.plot(range(0,bins),diagArray,'r',range(0,bins),hueHist2,'b')
        #plt.show()

        #cv2.imwrite('satmask.png',sMask*255.0)
        #cv2.imwrite('valmask.png',vMask*255.0)
        #cv2.imwrite('huemask.png',hMask*255.0)
        #print("Saved ----------------- SAVED ---------------- SAVED !!!!! %%%%%")

    dest=cv2.dilate(dest*1.0,np.ones((10,10)))
    dest=cv2.erode(dest*1.0,np.ones((10,10)))

    #cv2.imwrite('himg.png',image[:,:,0])

    #cv2.imwrite('object_segmented.png',dest*255.0)

    return cv2.convertScaleAbs(dest*255)

########################################################################################################################

def histThresh2(image, seedcolor, diagnostic):
    image = cv2.medianBlur(image, 9)
    image=cv2.cvtColor(image,cv2.cv.CV_RGB2HSV)
    image[:,:,0]*=255.0/180.0
    width = np.size(image,1)
    height = np.size(image,0)
    saturationCutoff=255*0.3
    valueCutoff=255*0.1
    windowsize=15

    dest=np.zeros((width, height))
    sMask=np.zeros((width, height))
    vMask=np.zeros((width, height))
    hMask=np.zeros((width, height))

    bins = 128
    valperbin = bins/255.0
    hueHist, nums=np.histogram(image[:,:,0],bins,(0,255))
    sMask=image[:,:,1]>saturationCutoff
    vMask=image[:,:,2]>valueCutoff

    hueHistOrig=hueHist
    hueHist2=medfilt(np.array(hueHist),3)

    hueHist=hueHist2

    localMinima = []
    for i in range(0,windowsize):
        window = hueHist[bins-1-windowsize+i:bins-1]+hueHist[0:i+windowsize]
        if hueHist[i] == min(window):
            localMinima += [i]

    for i in range(windowsize, bins-windowsize-1):
        window = hueHist[i-windowsize:i+windowsize]
        if hueHist[i] == min(window):
            localMinima += [i]

    for i in range(bins-windowsize, bins):
        window = hueHist[i-windowsize:bins-1]+hueHist[0:i+windowsize-bins]
        if hueHist[i] == min(window):
            localMinima += [i]

    if len(localMinima)==1:
        return cv2.convertScaleAbs(np.zeros((width, height)))

    modalityMeans = []
    meanAccumulator = 0
    numel = 0
    for i in range(0, len(localMinima)-1):
        for j in range(localMinima[i], localMinima[i+1]):
            meanAccumulator+=j*hueHist[j]
            numel+=hueHist[j]
        modalityMeans+=[1.0*meanAccumulator/numel]
        meanAccumulator = 0
        numel = 0

    for j in range(localMinima[len(localMinima)-1], bins)+range(0, localMinima[0]):
        meanAccumulator+=j*hueHist[j]
        numel+=hueHist[j]
    modalityMeans+=[1.0*meanAccumulator/numel]

    histSeed=round(255.0*seedcolor*valperbin)

    best = 0
    closest = abs(histSeed-modalityMeans[0])
    for i in range(1,len(modalityMeans)):
        if closest>abs(histSeed-modalityMeans[i]):
            best = i
            closest = abs(histSeed-modalityMeans[i])

    if (best == len(modalityMeans)-1):
        hMask=np.logical_or(image[:,:,0]>=localMinima[len(localMinima)-1]/valperbin,image[:,:,0]<=localMinima[0]/valperbin)
    else:
        hMask=np.logical_and(image[:,:,0]>=localMinima[best]/valperbin,image[:,:,0]<=localMinima[best+1]/valperbin)

    dest=np.logical_and(hMask,vMask)
    dest=np.logical_and(dest,sMask)

    modalityMeans = round(modalityMeans)
    if diagnostic:
        num = 10000
        diagArray = hueHist
        for i in range(0,bins):
            if i in modalityMeans:
                diagArray[i]=num+10000
            else:
                diagArray[i]=num
        if i in localMinima:
            if i == best:
                num = 20000
            else:
                if num ==10000:
                    num = 0
                else:
                    num = 10000

        plt.plot(range(0,bins),diagArray,'r',range(0,bins),hueHist2,'b')
        plt.show()

        cv2.imwrite('satmask.png',sMask*255.0)
        cv2.imwrite('valmask.png',vMask*255.0)
        cv2.imwrite('huemask.png',hMask*255.0)

    dest=cv2.dilate(dest*1.0,np.ones((10,10)))
    dest=cv2.erode(dest*1.0,np.ones((10,10)))

    cv2.imwrite('himg.png',image[:,:,0])

    cv2.imwrite('object_segmented.png',dest*255.0)

    return cv2.convertScaleAbs(dest*255)

class BlobProps:
    image=None
    centroids=None
    fi=None
    blobs=[]
    holes=[]
    blobBBs=[]
    holeBBs=[]
    blobHoleMat=[]
    volume=[]

    def __init__(self,image):
        self.image=image
                    ####################################################################################################
    #def cr(self,x,y,width,height):
        #return (x>0) and (y>0) and (x<width-1) and (y<height-1)
        #if tfcond:
        #    return (x>0) and (y>0) and (x<width-1) and (y<height-1) and labels[x,y]==0 and pixels[x,y]>0
        #else:
        #    return (x>0) and (y>0) and (x<width-1) and (y<height-1) and labels[x,y]==0 and pixels[x,y]==0
                    ####################################################################################################
    def extract2(self):
        im=self.image
        invimage=np.ones((np.size(im,0),np.size(im,1)))-im
        bloblabels=pymorph.label(im)
        holelabels=pymorph.label(invimage)
        print ("Image is ", (np.size(im,0),np.size(im,1)))
        self.blobs=[]  # pikseli predmeta
        self.holes=[]  # pikseli rupa
        for i in range(0,bloblabels.max()):
            self.blobs.append([])
        for i in range(0,holelabels.max()):
            self.holes.append([])
        for i in range(0,np.size(im,0)):
            for j in range(0,np.size(im,1)):
                if im[i][j]==1:
                    self.blobs[bloblabels[i][j]-1].append([i,j])  #
                else:                                             # Razdvajanje rupa i predmeta
                    self.holes[holelabels[i][j]-1].append([i,j])  #
                    ####################################################################################################
    def largeFilter(self,size,returnBlobs=True):
        idx=[]
        if returnBlobs:
            for i in range(0,len(self.blobs)):
                if len(self.blobs[i])<size:
                    idx.append(i)
            for i in range(0,len(idx)):
                self.blobs.pop(idx[i]-i)
        else:
            for i in range(0,len(self.holes)):
                if len(self.holes[i])<size:
                    idx.append(i)
            for i in range(0,len(idx)):
                self.holes.pop(idx[i]-i)
        self.changeThings()
                    ####################################################################################################
    def getCentroid(self, pointList):
        xtotal=0.0
        ytotal=0.0
        for i in range(0,len(pointList)):
            xtotal+=pointList[i][0]
            ytotal+=pointList[i][1]
        return [xtotal/len(pointList), ytotal/len(pointList)]
                    ####################################################################################################
    def getBBs(self, getBlobs=True):
        if getBlobs:
            self.blobBBs=[]
            for i in range(0,len(self.blobs)):
                xthi=-1
                xtlo=-1
                ythi=-1
                ytlo=-1
                for j in range(0,len(self.blobs[i])):
                    if (xthi==-1) or (self.blobs[i][j][0]>xthi):
                        xthi=self.blobs[i][j][0]
                    if (xtlo==-1) or (self.blobs[i][j][0]<xtlo):
                        xtlo=self.blobs[i][j][0]
                    if (ythi==-1) or (self.blobs[i][j][1]>ythi):
                        ythi=self.blobs[i][j][1]
                    if (ytlo==-1) or (self.blobs[i][j][1]<ytlo):
                        ytlo=self.blobs[i][j][1]
                self.blobBBs.append([xtlo,ytlo,xthi,ythi])
            return self.blobBBs
        else:
            self.holeBBs=[]
            for i in range(0,len(self.holes)):
                xthi=-1
                xtlo=-1
                ythi=-1
                ytlo=-1
                for j in range(0,len(self.holes[i])):
                    if (xthi==-1) or (self.holes[i][j][0]>xthi):
                        xthi=self.holes[i][j][0]
                    if (xtlo==-1) or (self.holes[i][j][0]<xtlo):
                        xtlo=self.holes[i][j][0]
                    if (ythi==-1) or (self.holes[i][j][1]>ythi):
                        ythi=self.holes[i][j][1]
                    if (ytlo==-1) or (self.holes[i][j][1]<ytlo):
                        ytlo=self.holes[i][j][1]
                self.holeBBs.append([xtlo,ytlo,xthi,ythi])
            return self.holeBBs
                    ####################################################################################################
    def getBlobHoleMat(self):
        self.getBBs(False)
        self.getBBs()

        self.blobHoleMat=np.zeros([len(self.blobBBs),len(self.holeBBs)])
        for i in range(0,len(self.blobBBs)):
            xlob=self.blobBBs[i][0]
            ylob=self.blobBBs[i][1]
            xhib=self.blobBBs[i][2]
            yhib=self.blobBBs[i][3]
            for j in range (0,len(self.holeBBs)):
                xloh=self.holeBBs[j][0]
                yloh=self.holeBBs[j][1]
                xhih=self.holeBBs[j][2]
                yhih=self.holeBBs[j][3]
                if xlob<xloh and ylob<yloh and yhib>yhih and xhib>xhih:
                    self.blobHoleMat[i][j]=1
                    ####################################################################################################
    def orientationGet(self):
        fi=[]
        for i in range(0,len(self.blobs)):
                m02=0
                m20=0
                m11=0
                m00=0
                m10=0
                m01=0
                for j in range(0,len(self.blobs[i])):
                           m01=m01+self.blobs[i][j][1]
                           m10=m10+self.blobs[i][j][0]
                           m00=m00+1
                xc=m10/m00
                yc=m01/m00
                for j in range(0,len(self.blobs[i])):
                         m02=m02+(self.blobs[i][j][1]-yc)^2
                         m20=m20+(self.blobs[i][j][0]-xc)^2
                         m11=m11+(self.blobs[i][j][1]-yc)*(self.blobs[i][j][0]-xc)
                fi.append(0.5*arctan2(2*m11,m20-m02))
        return fi

########################################################################################################################

def maxBlob(blob):
    maxblobs=0
    maxblobin=0
    for i in range(0, len(blob)):
        if len(blob[i])>maxblobs:
            maxblobs=len(blob[i])
            maxblobin=i
    return maxblobin

########################################################################################################################

def getBB(contour):
    xthi=-1
    xtlo=-1
    ythi=-1
    ytlo=-1
    for i in range(0,len(contour)):
        if (xthi==-1) or (contour[i][0][0]>xthi):
            xthi=contour[i][0][0]
        if (xtlo==-1) or (contour[i][0][0]<xtlo):
            xtlo=contour[i][0][0]
        if (ythi==-1) or (contour[i][0][1]>ythi):
            ythi=contour[i][0][1]
        if (ytlo==-1) or (contour[i][0][1]<ytlo):
            ytlo=contour[i][0][1]
    return [xtlo,ytlo,xthi,ythi]

def cmpBB_new(outer, inner):
    rightArea = (outer[2]-inner[2])*(inner[3]-inner[1])
    leftArea = (inner[0]- outer[0])*(inner[3]-inner[1])
    topArea = (inner[1]- outer[1])*(inner[2]-inner[0])
    bottomArea = (outer[3]-inner[3])*(inner[2]-inner[0])
    leftRight = abs(rightArea-leftArea)*1.0/max(rightArea,leftArea)
    if (rightArea<leftArea):
        leftRight*=-1.0
    upDown = abs(topArea-bottomArea)/max(topArea,bottomArea)
    if (topArea<bottomArea):
        upDown*=-1.0
    return [upDown,leftRight]

def cmpBB(outer, inner):
    bottomArea = (outer[2]-inner[2])*(inner[3]-inner[1])
    topArea = (inner[0]- outer[0])*(inner[3]-inner[1])
    leftArea = (inner[1]- outer[1])*(inner[2]-inner[0])
    rightArea = (outer[3]-inner[3])*(inner[2]-inner[0])
    leftRight = abs(rightArea-leftArea)*1.0/max(rightArea,leftArea)
    if (rightArea<leftArea):
        leftRight*=-1.0
    upDown = abs(topArea-bottomArea)/max(topArea,bottomArea)
    if (topArea<bottomArea):
        upDown*=-1.0
    return [upDown,leftRight]


########################################################################################################################

class NaoImgGetter:
    camProxy = None
    videoClient = None
    pilimage=None
    image=None
    def __init__(self, IP, PORT, cam):
        self.camProxy = ALProxy("ALVideoDevice", IP, PORT)
        try:
            self.camProxy.unsubscribe('python_client')
        except:
            pass
        resolution = 2 #VGA
        colorspace = 11 #RGB
        self.videoClient = self.camProxy.subscribe("python_client", resolution, colorspace, 5)
        self.camProxy.setActiveCamera("python_client", cam)

    def __del__(self):
        self.camProxy.unsubscribe(self.videoClient)

    def switchCamera(self, cam):
        self.camProxy.setActiveCamera(self.videoClient, cam)

    def end(self):
        self.camProxy.unsubscribe(self.videoClient)
                    ####################################################################################################
    def getImage(self, colorSpace=11):
        t0=time.time()
        self.camProxy.setColorSpace(self.videoClient,colorSpace)
        naoImage=self.camProxy.getImageRemote(self.videoClient)
        imageWidth = naoImage[0]
        imageHeight = naoImage[1]
        array = naoImage[6]
        self.pilimage = Image.fromstring("RGB", (imageWidth,imageHeight), array) #frombytes
        self.image=np.array(self.pilimage)
        al_image = self.camProxy.getImageRemote(self.videoClient)
        image_width = al_image[0]
        image_height = al_image[1]
        channels = al_image[2]
        img_data = al_image[6]
        image = np.array(np.frombuffer(img_data, dtype=np.uint8))  #
        image = image.reshape((image_height, image_width, channels))
        #print(image)
        #image = np.reshape(image, (image_width, image_height, channels))
        cv2.imwrite("Test.png", image)
        #self.image.resize((320,240),Image.ANTIALIAS)
        t1=time.time()
        print ('Image acquisition time =', str(t1-t0))
                    ####################################################################################################
    def cvGetImage(self):
        t0=time.time()
        self.camProxy.setColorSpace(self.videoClient,12) #HSV
        naoImage=self.camProxy.getImageRemote(self.videoClient)
        imageWidth = naoImage[0]
        imageHeight = naoImage[1]
        array = naoImage[6]
        self.cvimage = cv2.cv.CreateImageHeader((imageWidth,imageHeight),cv2.IPL_DEPTH_8U,3)
        cv2.cv.SetData(self.cvimage,array)
        t1=time.time()
        print ('Image acquisition time =', str(t1-t0))

############################################# MAIN #####################################################################
########################################################################################################################

if __name__ == '__main__2':
    im=cv2.imread("scene.png")
    im=cv2.cvtColor(im,cv2.cv.CV_RGB2HSV)
    bw=histThresh(im,0.2)
    blobProps=BlobProps(bw)
    blobProps.extract2()
    print (len(blobProps.blobs))
    print (len(blobProps.holes))
    #rgbhsvmat=np.zeros((256,256,256,3),np.float)
    #hsvfile=file('hsvMatrix.dat','w')
    #cPickle.dump(rgbhsvmat,hsvfile,2)
    #for r in range(0,256):
    #    print 'r=',r
    #    for g in range(0,256):
    #        for b in range(0,256):
    #            hsvpix=rgb2hsv(np.array([r,g,b],np.uint8))
    #            rgbhsvmat[r][g][b][0]=hsvpix[0]
    #            rgbhsvmat[r][g][b][1]=hsvpix[1]
    #            rgbhsvmat[r][g][b][2]=hsvpix[2]
    #a=1
    #hsvfile=file('hsvMatrix.dat','w')
    #cPickle.dump(rgbhsvmat,hsvfile,2)
    #hsvfile.close()

########################################################################################################################

if __name__ == '__main__':
    IP='Rene.local'
    PORT=9559
    t0=time.time()
    #nig=NaoImgGetter(IP,PORT)
    t1=time.time()
    print ('NAO connection time =', str(t1-t0))
    #nig.getImage(11)
    im=cv2.imread('ljepilo_grabpoint.png')
    im2=cv2.rectangle(im,(10,10),(100,100),(0,255,0))
    print (im2)
    cv2.imwrite('thing.png',im)
    cv2.imwrite('scene.png',im2)
    #nig.end()
    #bw=histThresh(nig.image,0.2)
    #blobProps=BlobProps(bw)
    #blobProps.extract2()
    #print len(blobProps.blobs)
    #print len(blobProps.holes)

