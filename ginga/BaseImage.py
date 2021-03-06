#
# BaseImage.py -- Abstraction of an generic data image.
#
# Eric Jeschke (eric@naoj.org) 
#
# Copyright (c) Eric R. Jeschke.  All rights reserved.
# This is open-source software licensed under a BSD license.
# Please see the file LICENSE.txt for details.
#
import math
import numpy
import logging

from ginga.misc import Bunch, Callback
from ginga import AutoCuts

class ImageError(Exception):
    pass

class BaseImage(Callback.Callbacks):

    def __init__(self, data_np=None, metadata=None, logger=None):

        Callback.Callbacks.__init__(self)
        
        if logger != None:
            self.logger = logger
        else:
            self.logger = logging.Logger('AstroImage')
        if data_np == None:
            data_np = numpy.zeros((1, 1))
        self._data = data_np
        self.metadata = {}
        if metadata:
            self.update_metadata(metadata)

        self._set_minmax()

        self.autocuts = AutoCuts.AutoCuts(self.logger)

        # For callbacks
        for name in ('modified', ):
            self.enable_callback(name)

    @property
    def width(self):
        # NOTE: numpy stores data in column-major layout
        data = self.get_data()
        return data.shape[1]
        
    @property
    def height(self):
        # NOTE: numpy stores data in column-major layout
        data = self.get_data()
        return data.shape[0]

    def get_size(self):
        return (self.width, self.height)
    
    def get_depth(self):
        data = self.get_data()
        if len(data.shape) > 2:
            return data.shape[2]
        return 1
    
    def get_shape(self):
        data = self.get_data()
        return data.shape
    
    def get_data(self):
        return self._data
        
    def copy_data(self):
        return self.get_data()
        
    def get_data_xy(self, x, y):
        data = self.get_data()
        val = data[y, x]
        return val
        
    def _get_dims(self, data):
        height, width = data.shape[:2]
        return (width, height)

    def get_metadata(self):
        return self.metadata.copy()
        
    def get_header(self):
        return self.get('exif', {})
        
    def get(self, kwd, *args):
        if self.metadata.has_key(kwd):
            return self.metadata[kwd]
        else:
            # return a default if there is one
            if len(args) > 0:
                return args[0]
            raise KeyError(kwd)
        
    def get_list(self, *args):
        return map(self.get, args)
    
    def __getitem__(self, kwd):
        return self.metadata[kwd]
        
    def update(self, kwds):
        self.metadata.update(kwds)
        
    def set(self, **kwds):
        self.update(kwds)
        
    def __setitem__(self, kwd, value):
        self.metadata[kwd] = value
        
    def set_data(self, data_np, metadata=None, astype=None):
        """Use this method to SHARE (not copy) the incoming array.
        """
        if astype:
            data = data_np.astype(astype)
        else:
            data = data_np
        self._data = data

        if metadata:
            self.update_metadata(metadata)
            
        self._set_minmax()

        self.make_callback('modified')

    def _set_minmax(self):
        data = self.get_data()
        self.maxval = numpy.nanmax(data)
        self.minval = numpy.nanmin(data)

        # TODO: see if there is a faster way to ignore infinity
        if numpy.isfinite(self.maxval):
            self.maxval_noinf = self.maxval
        else:
            try:
                self.maxval_noinf = numpy.nanmax(data[numpy.isfinite(data)])
            except:
                self.maxval_noinf = self.maxval
        
        if numpy.isfinite(self.minval):
            self.minval_noinf = self.minval
        else:
            try:
                self.minval_noinf = numpy.nanmin(data[numpy.isfinite(data)])
            except:
                self.minval_noinf = self.minval
        
    def get_minmax(self, noinf=False):
        if not noinf:
            return (self.minval, self.maxval)
        else:
            return (self.minval_noinf, self.maxval_noinf)

    def update_metadata(self, keyDict):
        for key, val in keyDict.items():
            self.metadata[key] = val

    def transfer(self, other, astype=None):
        data = self.get_data()
        other.set_data(data, metadata=self.metadata, astype=astype)
        
    def copy(self, astype=None):
        other = BaseImage()
        self.transfer(other, astype=astype)
        return other
        
    def cutout_data(self, x1, y1, x2, y2, astype=None):
        """cut out data area based on coords. 
        """
        data = self.get_data()
        data = data[y1:y2, x1:x2]
        if astype:
            data = data.astype(astype)
        return data
  
    def cutout_adjust(self, x1, y1, x2, y2, astype=None):
        dx = x2 - x1
        dy = y2 - y1
        
        if x1 < 0:
            x1 = 0; x2 = dx
        else:
            if x2 >= self.width:
                x2 = self.width
                x1 = x2 - dx
                
        if y1 < 0:
            y1 = 0; y2 = dy
        else:
            if y2 >= self.height:
                y2 = self.height
                y1 = y2 - dy

        data = self.cutout_data(x1, y1, x2, y2, astype=astype)
        return (data, x1, y1, x2, y2)

    def cutout_radius(self, x, y, radius, astype=None):
        return self.cutout_adjust(x-radius, y-radius,
                                  x+radius+1, y+radius+1,
                                  astype=astype)

    def get_scaled_cutout_wdht(self, x1, y1, x2, y2, new_wd, new_ht):

        # calculate dimensions of NON-scaled cutout
        old_wd = x2 - x1 + 1
        old_ht = y2 - y1 + 1
        self.logger.debug("old=%dx%d new=%dx%d" % (
            old_wd, old_ht, new_wd, new_ht))

        data = self.get_data()
        
        # Is there a more efficient way to do this?
        yi, xi = numpy.mgrid[0:new_ht, 0:new_wd]
        iscale_x = float(old_wd) / float(new_wd)
        iscale_y = float(old_ht) / float(new_ht)
            
        xi *= iscale_x 
        yi *= iscale_y
        cutout = data[y1:y2+1, x1:x2+1]
        ht, wd = cutout.shape[:2]
        xi = xi.astype('int').clip(0, wd-1)
        yi = yi.astype('int').clip(0, ht-1)
        newdata = cutout[yi, xi]
        ht, wd = newdata.shape[:2]
        scale_x = float(wd) / dx
        scale_y = float(ht) / dy
        res = Bunch.Bunch(data=newdata, org_fac=1,
                          scale_x=scale_x, scale_y=scale_y)
        return res

    def get_scaled_cutout_basic(self, x1, y1, x2, y2, scale_x, scale_y):

        # calculate dimensions of NON-scaled cutout
        old_wd = x2 - x1 + 1
        old_ht = y2 - y1 + 1
        # calculate dimensions of scaled cutout
        new_wd = int(round(scale_x * old_wd))
        new_ht = int(round(scale_y * old_ht))
        self.logger.debug("old=%dx%d new=%dx%d" % (
            old_wd, old_ht, new_wd, new_ht))

        data = self.get_data()
        
        # Is there a more efficient way to do this?
        yi, xi = numpy.mgrid[0:new_ht, 0:new_wd]
        iscale_x = float(old_wd) / float(new_wd)
        iscale_y = float(old_ht) / float(new_ht)
            
        xi *= iscale_x 
        yi *= iscale_y
        cutout = data[y1:y2+1, x1:x2+1]
        ht, wd = cutout.shape[:2]
        xi = xi.astype('int').clip(0, wd-1)
        yi = yi.astype('int').clip(0, ht-1)
        newdata = cutout[yi, xi]
        ht, wd = newdata.shape[:2]
        scale_x = float(wd) / old_wd
        scale_y = float(ht) / old_ht
        res = Bunch.Bunch(data=newdata, org_fac=1,
                          scale_x=scale_x, scale_y=scale_y)
        return res

    def get_scaled_cutout_by_dims(self, x1, y1, x2, y2, dst_wd, dst_ht,
                                  method='basic'):
        if method == 'basic':
            return self.get_scaled_cutout_wdht(x1, y1, x2, y2, dst_wd, dst_ht)

        raise ImageError("Method not supported: '%s'" % (method))
    
    def get_scaled_cutout(self, x1, y1, x2, y2, scale_x, scale_y,
                          method='basic'):
        if method == 'basic':
            return self.get_scaled_cutout_basic(x1, y1, x2, y2,
                                                 scale_x, scale_y)

        raise ImageError("Method not supported: '%s'" % (method))

    
    def histogram(self, x1, y1, x2, y2, z=None, pct=1.0, numbins=2048):
        data = self.get_data()
        if z != None:
            data = data[y1:y2, x1:x2, z]
        else:
            data = data[y1:y2, x1:x2]

        return self.autocuts.calc_histogram(data, pct=pct, numbins=numbins)

    def cut_levels(self, loval, hival, vmin=0.0, vmax=255.0):
        data = self.get_data()
        data = self.autocuts.cut_levels(data, loval, hival,
                                        vmin=vmin, vmax=vmax)
        self.set_data(data)

    def transform(self, flip_x=False, flip_y=False, swap_xy=False):
        data = self.get_data()

        # Do transforms as necessary
        if flip_y:
            data = numpy.flipud(data)
        if flip_x:
            data = numpy.fliplr(data)
        if swap_xy:
            data = data.swapaxes(0, 1)
            
        self.set_data(data)
            
    def info_xy(self, data_x, data_y):
        # Get the value under the data coordinates
        try:
            value = self.get_data_xy(int(data_x), int(data_y))

        except Exception, e:
            value = None

        info = Bunch.Bunch(itype='base', data_x=data_x, data_y=data_y,
                           x=data_x, y=data_y,
                           value=value)
        return info

#END
