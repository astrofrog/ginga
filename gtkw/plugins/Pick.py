#
# Pick.py -- Pick plugin for fits viewer
# 
#[ Eric Jeschke (eric@naoj.org) --
#  Last edit: Fri Jun 22 13:44:51 HST 2012
#]
#
# Copyright (c) 2011-2012, Eric R. Jeschke.  All rights reserved.
# This is open-source software licensed under a BSD license.
# Please see the file LICENSE.txt for details.
#
import gtk
import pango
import GtkHelp
import iqcalc
import Bunch

import numpy
try:
    import matplotlib
    matplotlib.use('GTKCairo')
    from  matplotlib.backends.backend_gtkcairo import FigureCanvasGTKCairo \
         as FigureCanvas
    have_mpl = True
except ImportError:
    have_mpl = False

import FitsImageCanvasGtk
import FitsImageCanvasTypesGtk as CanvasTypes
import GingaPlugin

region_default_width = 30
region_default_height = 30


class Pick(GingaPlugin.LocalPlugin):

    def __init__(self, fv, fitsimage):
        # superclass defines some variables for us, like logger
        super(Pick, self).__init__(fv, fitsimage)

        self.layertag = 'pick-canvas'
        self.pickimage = None
        self.pickcenter = None
        self.pick_qs = None
        self.picktag = None
        self.pickcolor = 'green'

        self.pick_x1 = 0
        self.pick_y1 = 0
        self.pick_data = None
        self.dx = region_default_width
        self.dy = region_default_height
        # this is the maximum size a side can be
        self.max_len = 1024
        self.radius = 10
        self.show_candidates = False

        self.plot_panx = 0.5
        self.plot_pany = 0.5
        self.plot_zoomlevel = 1.0
        self.num_contours = 8
        self.delta_sky = 0.0
        self.delta_bright = 0.0
        self.iqcalc = iqcalc.IQCalc(self.logger)

        canvas = CanvasTypes.DrawingCanvas()
        canvas.enable_draw(True)
        canvas.set_callback('button-press', self.btndown)
        canvas.set_callback('motion', self.drag)
        canvas.set_callback('button-release', self.update)
        canvas.set_drawtype('rectangle', color='cyan', linestyle='dash',
                            drawdims=True)
        canvas.set_callback('draw-event', self.setpickregion)
        canvas.setSurface(self.fitsimage)
        self.canvas = canvas

        self.w.tooltips = self.fv.w.tooltips

    def build_gui(self, container):
        self.pickcenter = None

        vpaned = gtk.VPaned()

        nb = gtk.Notebook()
        #nb.set_group_id(group)
        #nb.connect("create-window", self.detach_page, group)
        nb.set_tab_pos(gtk.POS_RIGHT)
        nb.set_scrollable(True)
        nb.set_show_tabs(True)
        nb.set_show_border(False)
        self.w.nb1 = nb
        vpaned.pack1(nb, resize=True, shrink=True)
        
        cm, im = self.fv.cm, self.fv.im

        di = FitsImageCanvasGtk.FitsImageCanvas(logger=self.logger)
        di.enable_autoscale('off')
        di.enable_autolevels('off')
        di.enable_zoom(True)
        di.enable_cuts(True)
        #di.set_zoom_limits(1, 20)
        di.zoom_to(3, redraw=False)
        di.set_callback('zoom-set', self.zoomset)
        di.set_cmap(cm, redraw=False)
        di.set_imap(im, redraw=False)
        di.set_callback('motion', self.detailxy)
        di.set_bg(0.4, 0.4, 0.4)
        self.pickimage = di

        iw = di.get_widget()
        width, height = 200, 200
        iw.set_size_request(width, height)
        label = gtk.Label('Image')
        label.show()
        nb.append_page(iw, label)
        nb.set_tab_reorderable(iw, True)
        #nb.set_tab_detachable(iw, True)

        if have_mpl:
            self.w.fig = matplotlib.figure.Figure()
            self.w.ax = self.w.fig.add_subplot(111, axisbg='black')
            self.w.ax.set_aspect('equal', adjustable='box')
            #self.w.ax.set_xlabel('X values')
            #self.w.ax.set_ylabel('Y values')
            self.w.ax.set_title('Contours')
            #self.w.ax.grid(True)
            canvas = FigureCanvas(self.w.fig)
            #canvas.set_size_request(width, height)
            self.w.canvas = canvas
            self.w.canvas.show_all()
            canvas.connect("scroll_event", self.plot_scroll)
            #canvas.connect("key_press_event", self.pan_plot)
            canvas.connect("motion_notify_event", self.plot_motion_notify)
            canvas.connect("button_press_event", self.plot_button_press)
            canvas.connect("button_release_event", self.plot_button_release)

            label = gtk.Label('Contour')
            label.show()
            nb.append_page(canvas, label)
            nb.set_tab_reorderable(canvas, True)
            #nb.set_tab_detachable(canvas, True)

            self.w.fig2 = matplotlib.figure.Figure()
            self.w.ax2 = self.w.fig2.add_subplot(111, axisbg='white')
            #self.w.ax2.set_aspect('equal', adjustable='box')
            self.w.ax2.set_ylabel('brightness')
            self.w.ax2.set_xlabel('pixels')
            self.w.ax2.set_title('FWHM')
            self.w.ax.grid(True)
            canvas = FigureCanvas(self.w.fig2)
            #canvas.set_size_request(width, height)
            self.w.canvas2 = canvas
            self.w.canvas2.show_all()

            label = gtk.Label('FWHM')
            label.show()
            nb.append_page(canvas, label)
            nb.set_tab_reorderable(canvas, True)
            #nb.set_tab_detachable(canvas, True)

        sw = gtk.ScrolledWindow()
        sw.set_border_width(2)
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        vbox = gtk.VBox()
        sw.add_with_viewport(vbox)

        self.msgFont = pango.FontDescription("Sans 14")
        tw = gtk.TextView()
        tw.set_wrap_mode(gtk.WRAP_WORD)
        tw.set_left_margin(4)
        tw.set_right_margin(4)
        tw.set_editable(False)
        tw.set_left_margin(4)
        tw.set_right_margin(4)
        tw.modify_font(self.msgFont)
        self.tw = tw

        fr = gtk.Frame(" Instructions ")
        fr.set_shadow_type(gtk.SHADOW_ETCHED_OUT)
        fr.set_label_align(0.1, 0.5)
        fr.add(tw)
        vbox.pack_start(fr, padding=4, fill=True, expand=False)
        
        fr = gtk.Frame(" Pick ")
        fr.set_shadow_type(gtk.SHADOW_ETCHED_OUT)
        fr.set_label_align(0.1, 0.5)

        nb = gtk.Notebook()
        #nb.set_group_id(group)
        #nb.connect("create-window", self.detach_page, group)
        nb.set_tab_pos(gtk.POS_BOTTOM)
        nb.set_scrollable(True)
        nb.set_show_tabs(True)
        nb.set_show_border(False)
        self.w.nb2 = nb
        fr.add(nb)
        vbox.pack_start(fr, padding=4, fill=True, expand=False)

        # Build report panel
        captions = (('Zoom', 'label', 'Contour Zoom', 'label'),
            ('Object_X', 'label', 'Object_Y', 'label'),
            ('RA', 'label', 'DEC', 'label'), ('Equinox', 'label'),
            ('Sky Level', 'label', 'Brightness', 'label'), 
            ('FWHM', 'label', 'Star Size', 'label'),
            ('Sample Area', 'label', 'Default Region', 'button'),
            ('Sky cut', 'button', 'Delta sky', 'entry'),
            ('Bright cut', 'button', 'Delta bright', 'entry'),
            )

        w, b = GtkHelp.build_info(captions)
        self.w.update(b)
        b.zoom.set_text(self.fv.scale2text(di.get_scale()))
        self.wdetail = b
        b.default_region.connect('clicked', lambda w: self.reset_region())
        self.w.tooltips.set_tip(b.default_region,
                                   "Reset region size to default")
        self.w.tooltips.set_tip(b.sky_cut, "Set image low cut to Sky Level")
        self.w.tooltips.set_tip(b.delta_sky, "Delta to apply to low cut")
        self.w.tooltips.set_tip(b.bright_cut,
                                "Set image high cut to Sky Level+Brightness")
        self.w.tooltips.set_tip(b.delta_bright, "Delta to apply to high cut")

        b.sky_cut.set_sensitive(False)
        self.w.btn_sky_cut = b.sky_cut
        self.w.btn_sky_cut.connect('clicked', lambda w: self.sky_cut())
        self.w.sky_cut_delta = b.delta_sky
        b.delta_sky.set_text(str(self.delta_sky))
        b.bright_cut.set_sensitive(False)
        self.w.btn_bright_cut = b.bright_cut
        self.w.btn_bright_cut.connect('clicked', lambda w: self.bright_cut())
        self.w.bright_cut_delta = b.delta_bright
        b.delta_bright.set_text(str(self.delta_bright))

        label = gtk.Label("Report")
        label.show()
        nb.append_page(w, label)
        nb.set_tab_reorderable(w, True)
        #nb.set_tab_detachable(w, True)

        # Build settings panel
        captions = (('Show Candidates', 'checkbutton'),
            ('Radius', 'entry', 'Threshold', 'entry'),
            )

        w, b = GtkHelp.build_info(captions)
        self.w.update(b)
        self.w.tooltips.set_tip(b.radius, "Radius for peak detection")
        self.w.tooltips.set_tip(b.threshold, "Threshold for peak detection (blank=default)")
        self.w.tooltips.set_tip(b.show_candidates,
                                "Show all peak candidates")
        b.radius.set_text(str(self.radius))
        b.show_candidates.set_active(self.show_candidates)
        b.show_candidates.connect('toggled', self.show_candidates_cb)

        label = gtk.Label("Settings")
        label.show()
        nb.append_page(w, label)
        nb.set_tab_reorderable(w, True)
        #nb.set_tab_detachable(w, True)

        btns = gtk.HButtonBox()
        btns.set_layout(gtk.BUTTONBOX_START)
        btns.set_spacing(3)
        btns.set_child_size(15, -1)

        btn = gtk.Button("Close")
        btn.connect('clicked', lambda w: self.close())
        btns.add(btn)
        vbox.pack_start(btns, padding=4, fill=True, expand=False)

        vpaned.pack2(sw, resize=True, shrink=True)
        vpaned.set_position(280)
        vpaned.show_all()
        
        container.pack_start(vpaned, padding=0, fill=True, expand=True)

    def plot_panzoom(self):
        ht, wd = self.pick_data.shape
        x = int(self.plot_panx * wd)
        y = int(self.plot_pany * ht)

        if self.plot_zoomlevel >= 1.0:
            scalefactor = 1.0 / self.plot_zoomlevel
        elif self.plot_zoomlevel < -1.0:
            scalefactor = - self.plot_zoomlevel
        else:
            # wierd condition?--reset to 1:1
            scalefactor = 1.0
            self.plot_zoomlevel = 1.0

        # Show contour zoom level
        text = self.fv.scale2text(1.0/scalefactor)
        self.wdetail.contour_zoom.set_text(text)

        xdelta = int(scalefactor * (wd/2.0))
        ydelta = int(scalefactor * (ht/2.0))
        xlo, xhi = x-xdelta, x+xdelta
        # distribute remaining x space from plot
        if xlo < 0:
            xsh = abs(xlo)
            xlo, xhi = 0, min(wd-1, xhi+xsh)
        elif xhi >= wd:
            xsh = xhi - wd
            xlo, xhi = max(0, xlo-xsh), wd-1
        self.w.ax.set_xlim(xlo, xhi)

        ylo, yhi = y-ydelta, y+ydelta
        # distribute remaining y space from plot
        if ylo < 0:
            ysh = abs(ylo)
            ylo, yhi = 0, min(ht-1, yhi+ysh)
        elif yhi >= ht:
            ysh = yhi - ht
            ylo, yhi = max(0, ylo-ysh), ht-1
        self.w.ax.set_ylim(ylo, yhi)

        self.w.fig.canvas.draw()

    def plot_contours(self):
        # Make a contour plot
        ht, wd = self.pick_data.shape
        self.w.ax.cla()
        try:
            # Create a contour plot
            xarr = numpy.arange(wd)
            yarr = numpy.arange(ht)
            self.w.ax.contourf(xarr, yarr, self.pick_data,
                               self.num_contours)
            # Mark the center of the object
            x, y = self.pickcenter.x, self.pickcenter.y
            self.w.ax.plot([x], [y], marker='x', ms=20.0,
                           color='black')

            # Set the pan and zoom position & redraw
            self.plot_panzoom()
            
        except Exception, e:
            self.logger.error("Error making contour plot: %s" % (
                str(e)))

    def _plot_fwhm_axis(self, arr, medv, color1, color2, color3):
        N = len(arr)
        X = numpy.array(range(N))
        Y = arr
        # subtract sky background
        ## medv = numpy.median(Y)
        Y = Y - medv
        maxv = Y.max()
        # clamp to 0..max
        Y = Y.clip(0, maxv)
        self.logger.debug("Y=%s" % (str(Y)))
        self.w.ax2.plot(X, Y, color=color1, marker='.')

        fwhm, mu, sdev, maxv = self.iqcalc.calc_fwhm(arr)
        Z = numpy.array([self.iqcalc.gaussian(x, (mu, sdev, maxv)) for x in X])
        self.w.ax2.plot(X, Z, color=color1, linestyle=':')
        self.w.ax2.axvspan(mu-fwhm/2.0, mu+fwhm/2.0,
                           facecolor=color3, alpha=0.25)
        return (fwhm, mu, sdev, maxv)

    def plot_fwhm(self, qs):
        # Make a FWHM plot
        self.w.ax2.cla()
        x, y, radius = qs.x, qs.y, qs.fwhm_radius
        try:
            image = self.fitsimage.get_image()
            x0, y0, xarr, yarr = image.cutout_cross(x, y, radius)

            # get median value from the cutout area
            medv = numpy.median(self.pick_data)
            self.logger.debug("cutting x=%d y=%d r=%d med=%f" % (
                x, y, radius, medv))
            
            self.logger.debug("xarr=%s" % (str(xarr)))
            fwhm_x, mu, sdev, maxv = self._plot_fwhm_axis(xarr, medv,
                                                          'blue', 'blue', 'skyblue')

            self.logger.debug("yarr=%s" % (str(yarr)))
            fwhm_y, mu, sdev, maxv = self._plot_fwhm_axis(yarr, medv,
                                                          'green', 'green', 'seagreen')
            
            self.w.fig2.canvas.draw()
        except Exception, e:
            self.logger.error("Error making fwhm plot: %s" % (
                str(e)))

    def close(self):
        chname = self.fv.get_channelName(self.fitsimage)
        self.fv.stop_operation_channel(chname, str(self))
        return True
        
    def instructions(self):
        buf = self.tw.get_buffer()
        buf.set_text("""Left-click to place region.  Left-drag to position region.  Redraw region with the right mouse button.""")
        self.tw.modify_font(self.msgFont)
            
    def start(self):
        self.instructions()
        # insert layer if it is not already
        try:
            obj = self.fitsimage.getObjectByTag(self.layertag)

        except KeyError:
            # Add canvas layer
            self.fitsimage.add(self.canvas, tag=self.layertag)
            
        self.resume()

    def pause(self):
        self.canvas.ui_setActive(False)
        
    def resume(self):
        self.canvas.ui_setActive(True)
        self.fv.showStatus("Draw a rectangle with the right mouse button")
        
    def stop(self):
        # remove the canvas from the image
        self.canvas.ui_setActive(False)
        try:
            self.fitsimage.deleteObjectByTag(self.layertag)
        except:
            pass
        self.fv.showStatus("")
        
    def redo(self):
        obj = self.canvas.getObjectByTag(self.picktag)
        if obj.kind != 'compound':
            return True
        bbox  = obj.objects[0]
        point = obj.objects[1]
        data_x, data_y = point.x, point.y

        # set the pick image to have the same cut levels and transforms
        self.fitsimage.copy_attributes(self.pickimage,
                                       ['transforms', 'cutlevels',
                                        'rgbmap'],
                                       redraw=False)
        
        try:
            image = self.fitsimage.get_image()

            # sanity check on region
            width = bbox.x2 - bbox.x1
            height = bbox.y2 - bbox.y1
            if (width > self.max_len) or (height > self.max_len):
                errmsg = "Image area (%dx%d) too large!" % (
                    width, height)
                self.fv.showStatus(errmsg)
                raise Exception(errmsg)
        
            # Note: FITS coordinates are 1-based, whereas numpy FITS arrays
            # are 0-based
            fits_x, fits_y = data_x + 1, data_y + 1

            # Cut and show pick image in pick window
            #self.pick_x, self.pick_y = data_x, data_y
            self.logger.debug("bbox %f,%f %f,%f" % (bbox.x1, bbox.y1,
                                                    bbox.x2, bbox.y2))
            x1, y1, x2, y2, data = self.cutdetail(self.fitsimage,
                                                  self.pickimage,
                                                  int(bbox.x1), int(bbox.y1),
                                                  int(bbox.x2), int(bbox.y2))
            self.logger.debug("cut box %f,%f %f,%f" % (x1, y1, x2, y2))

            # calculate center of pick image
            wd, ht = self.pickimage.get_data_size()
            xc = wd // 2
            yc = ht // 2
            if not self.pickcenter:
                tag = self.pickimage.add(CanvasTypes.Point(xc, yc, 5,
                                                           linewidth=1,
                                                           color='red'))
                self.pickcenter = self.pickimage.getObjectByTag(tag)
            
            self.pick_x1, self.pick_y1 = x1, y1
            self.pick_data = data
            self.wdetail.sample_area.set_text('%dx%d' % (x2-x1, y2-y1))

            point.color = 'red'
            self.pickcenter.x = xc
            self.pickcenter.y = yc
            self.pickcenter.color = 'red'

            # Get parameters for peak finding
            radius = int(self.w.radius.get_text())
            threshold = None
            ths = self.w.threshold.get_text().strip()
            if len(ths) > 0:
                threshold = float(ths)
                
            # Delete previous peak marks
            objs = self.fitsimage.getObjectsByTagpfx('peak')
            self.fitsimage.deleteObjects(objs, redraw=False)

            # Find bright peaks in the cutout
            peaks = self.iqcalc.find_bright_peaks(data, threshold=threshold,
                                                  radius=radius)
            if len(peaks) == 0:
                raise Exception("Cannot find bright peaks")
                
            # Evaluate those peaks
            objlist = self.iqcalc.evaluate_peaks(peaks, data,
                                                 bright_radius=radius,
                                                 fwhm_radius=radius)
            if len(objlist) == 0:
                raise Exception("Error evaluating bright peaks")

            # Mark new peaks, if desired
            if self.show_candidates:
                for obj in objlist:
                    tag = self.fitsimage.add(CanvasTypes.Point(x1+obj.objx,
                                                               y1+obj.objy,
                                                               5,
                                                               linewidth=1,
                                                               color='purple'),
                                             tagpfx='peak', redraw=False)

            height, width = data.shape
            qs = self.iqcalc.objlist_select(objlist, width, height)

            # Add back in offsets into image to get correct values with respect
            # to the entire image
            qs.x += x1
            qs.y += y1
            qs.objx += x1
            qs.objy += y1
            ## qs = image.qualsize(x1, y1, x2, y2, radius=radius,
            ##                     threshold=threshold)

            # Calculate X/Y of center of star
            obj_x = qs.objx
            obj_y = qs.objy
            fwhm = qs.fwhm
            fwhm_x, fwhm_y = qs.fwhm_x, qs.fwhm_y
            rnd_x, rnd_y = int(round(qs.objx)), int(round(qs.objy))
            #point.x, point.y = rnd_x, rnd_y
            point.x, point.y = obj_x, obj_y

            self.wdetail.fwhm.set_text('%.3f' % fwhm)
            self.wdetail.object_x.set_text('%.3f' % (obj_x+1))
            self.wdetail.object_y.set_text('%.3f' % (obj_y+1))
            self.wdetail.sky_level.set_text('%.3f' % qs.skylevel)
            self.wdetail.brightness.set_text('%.3f' % qs.brightness)

            self.w.btn_sky_cut.set_sensitive(True)
            self.w.btn_bright_cut.set_sensitive(True)
            
            # Mark center of object on pick image
            i1 = point.x - x1
            j1 = point.y - y1
            self.pickcenter.x = i1
            self.pickcenter.y = j1
            self.pickcenter.color = 'cyan'
            self.pick_qs = qs

            # Mark object center on image
            point.color = 'cyan'
            self.fitsimage.panset_xy(rnd_x, rnd_y, redraw=False)

            # Calc RA, DEC, EQUINOX of X/Y center pixel
            try:
                ra_txt, dec_txt = image.pixtoradec(obj_x, obj_y, format='str')
            except Exception, e:
                ra_txt = 'WCS ERROR'
                dec_txt = 'WCS ERROR'
            self.wdetail.ra.set_text(ra_txt)
            self.wdetail.dec.set_text(dec_txt)

            equinox = image.get_keyword('EQUINOX', 'UNKNOWN')
            self.wdetail.equinox.set_text(str(equinox))

            # TODO: Get separate FWHM for X and Y
            try:
                cdelt1, cdelt2 = image.get_keywords_list('CDELT1', 'CDELT2')
                starsize = self.iqcalc.starsize(fwhm_x, cdelt1, fwhm_y, cdelt2)
                self.wdetail.star_size.set_text('%.3f' % starsize)
            except Exception, e:
                self.wdetail.star_size.set_text('ERROR')
                self.fv.showStatus("Couldn't calculate star size: %s" % (
                    str(e)))

            self.plot_panx = float(i1) / wd
            self.plot_pany = float(j1) / ht
            if have_mpl:
                self.plot_contours()
                self.plot_fwhm(qs)
            
        except Exception, e:
            self.logger.error("Error calculating quality metrics: %s" % (
                str(e)))
            for key in ('sky_level', 'brightness', 'star_size'):
                self.wdetail[key].set_text('')
            self.wdetail.fwhm.set_text('Failed')
            self.w.btn_sky_cut.set_sensitive(False)
            self.w.btn_bright_cut.set_sensitive(False)
            self.pick_qs = None

            self.plot_panx = self.plot_pany = 0.5
            self.plot_contours()
            # TODO: could calc background based on numpy calc

        self.pickimage.redraw(whence=3)
        self.canvas.redraw(whence=3)
        
        self.fv.showStatus("Click left mouse button to reposition pick")
        return True
    
    def btndown(self, canvas, button, data_x, data_y):
        if not (button == 0x1):
            return
        
        try:
            obj = self.canvas.getObjectByTag(self.picktag)
            if obj.kind == 'rectangle':
                bbox = obj
            else:
                bbox  = obj.objects[0]
                point = obj.objects[1]
            self.dx = (bbox.x2 - bbox.x1) // 2
            self.dy = (bbox.y2 - bbox.y1) // 2
        except Exception, e:
            pass

        dx = self.dx
        dy = self.dy
        
        # Mark center of object and region on main image
        try:
            self.canvas.deleteObjectByTag(self.picktag, redraw=False)
        except:
            pass

        x1, y1 = data_x - dx, data_y - dy
        x2, y2 = data_x + dx, data_y + dy
        
        tag = self.canvas.add(CanvasTypes.Rectangle(x1, y1, x2, y2,
                                                    color='cyan',
                                                    linestyle='dash'))
        self.picktag = tag

        #self.setpickregion(self.canvas, tag)
        
    def update(self, canvas, button, data_x, data_y):
        if not (button == 0x1):
            return
        
        try:
            obj = self.canvas.getObjectByTag(self.picktag)
            if obj.kind == 'rectangle':
                bbox = obj
            else:
                bbox  = obj.objects[0]
                point = obj.objects[1]
            self.dx = (bbox.x2 - bbox.x1) // 2
            self.dy = (bbox.y2 - bbox.y1) // 2
        except Exception, e:
            obj = None
            pass

        dx = self.dx
        dy = self.dy
        
        x1, y1 = data_x - dx, data_y - dy
        x2, y2 = data_x + dx, data_y + dy
        
        if (not obj) or (obj.kind == 'compound'):
            # Replace compound image with rectangle
            try:
                self.canvas.deleteObjectByTag(self.picktag, redraw=False)
            except:
                pass

            tag = self.canvas.add(CanvasTypes.Rectangle(x1, y1, x2, y2,
                                                        color='cyan',
                                                        linestyle='dash'),
                                  redraw=False)
        else:
            # Update current rectangle with new coords
            bbox.x1, bbox.y1, bbox.x2, bbox.y2 = x1, y1, x2, y2
            tag = self.picktag

        self.setpickregion(self.canvas, tag)

        
    def drag(self, canvas, button, data_x, data_y):
        if not (button == 0x1):
            return

        obj = self.canvas.getObjectByTag(self.picktag)
        if obj.kind == 'compound':
            bbox = obj.objects[0]
        elif obj.kind == 'rectangle':
            bbox = obj
        else:
            return True

        # calculate center of bbox
        wd = bbox.x2 - bbox.x1
        dw = wd // 2
        ht = bbox.y2 - bbox.y1
        dh = ht // 2
        x, y = bbox.x1 + dw, bbox.y1 + dh

        # calculate offsets of move
        dx = (data_x - x)
        dy = (data_y - y)

        # calculate new coords
        x1, y1, x2, y2 = bbox.x1+dx, bbox.y1+dy, bbox.x2+dx, bbox.y2+dy

        if (not obj) or (obj.kind == 'compound'):
            # Replace compound image with rectangle
            try:
                self.canvas.deleteObjectByTag(self.picktag, redraw=False)
            except:
                pass

            self.picktag = self.canvas.add(CanvasTypes.Rectangle(x1, y1, x2, y2,
                                                                 color='cyan',
                                                                 linestyle='dash'))
        else:
            # Update current rectangle with new coords and redraw
            bbox.x1, bbox.y1, bbox.x2, bbox.y2 = x1, y1, x2, y2
            self.canvas.redraw(whence=3)


    def setpickregion(self, canvas, tag):
        obj = canvas.getObjectByTag(tag)
        if obj.kind != 'rectangle':
            return True
        canvas.deleteObjectByTag(tag, redraw=False)

        if self.picktag:
            try:
                canvas.deleteObjectByTag(self.picktag, redraw=False)
            except:
                pass

        # determine center of rectangle
        x = obj.x1 + (obj.x2 - obj.x1) // 2
        y = obj.y1 + (obj.y2 - obj.y1) // 2
        
        tag = canvas.add(CanvasTypes.CompoundObject(
            CanvasTypes.Rectangle(obj.x1, obj.y1, obj.x2, obj.y2,
                                  color=self.pickcolor),
            CanvasTypes.Point(x, y, 10, color='red'),
            CanvasTypes.Text(obj.x1, obj.y2+4, "Pick",
                             color=self.pickcolor)),
                         redraw=False)
        self.picktag = tag

        #self.fv.raise_tab("detail")
        return self.redo()
    
    def reset_region(self):
        self.dx = region_default_width
        self.dy = region_default_height

        obj = self.canvas.getObjectByTag(self.picktag)
        if obj.kind != 'compound':
            return True
        bbox = obj.objects[0]
    
        # calculate center of bbox
        wd = bbox.x2 - bbox.x1
        dw = wd // 2
        ht = bbox.y2 - bbox.y1
        dh = ht // 2
        x, y = bbox.x1 + dw, bbox.y1 + dh

        # calculate new coords
        bbox.x1, bbox.y1, bbox.x2, bbox.y2 = (x-self.dx, y-self.dy,
                                              x+self.dx, y+self.dy)

        self.redo()


    def sky_cut(self):
        if not self.pick_qs:
            self.fv.showStatus("Please pick an object to set the sky level!")
            return
        loval = self.pick_qs.skylevel
        delta = self.w.sky_cut_delta.get_text()
        if len(delta) == 0:
            delta = 0.0
        oldlo, hival = self.fitsimage.get_cut_levels()
        try:
            self.delta_sky = float(delta)
            loval += self.delta_sky
            self.fitsimage.cut_levels(loval, hival)
            
        except Exception, e:
            self.fv.showStatus("No valid sky level: '%s'" % (loval))
            
    def bright_cut(self):
        if not self.pick_qs:
            self.fv.showStatus("Please pick an object to set the brightness!")
            return
        skyval = self.pick_qs.skylevel
        hival = self.pick_qs.brightness
        delta = self.w.bright_cut_delta.get_text()
        if len(delta) == 0:
            delta = 0.0
        loval, oldhi = self.fitsimage.fitsimage.get_cut_levels()
        try:
            self.delta_bright = float(delta)
            # brightness is measured ABOVE sky level
            hival = skyval + hival + self.delta_bright
            self.fitsimage.cut_levels(loval, hival)
            
        except Exception, e:
            self.fv.showStatus("No valid brightness level: '%s'" % (hival))
            
    def zoomset(self, fitsimage, zoomlevel, scalefactor):
        self.logger.debug("scalefactor = %.2f" % (scalefactor))
        text = self.fv.scale2text(scalefactor)
        self.wdetail.zoom.set_text(text)

    def detailxy(self, canvas, button, data_x, data_y):
        """Motion event in the pick fits window.  Show the pointing
        information under the cursor.
        """
        if button == 0:
            # TODO: we could track the focus changes to make this check
            # more efficient
            fitsimage = self.fv.getfocus_fitsimage()
            # Don't update global information if our fitsimage isn't focused
            if fitsimage != self.fitsimage:
                return True
        
            # Add offsets from cutout
            data_x = data_x + self.pick_x1
            data_y = data_y + self.pick_y1

            return self.fv.showxy(self.fitsimage, data_x, data_y)

    def cutdetail(self, srcimage, dstimage, x1, y1, x2, y2, redraw=True):
        image = srcimage.get_image()
        data, x1, y1, x2, y2 = image.cutout_adjust(x1, y1, x2, y2)

        dstimage.set_data(data, redraw=redraw)

        return (x1, y1, x2, y2, data)

    def show_candidates_cb(self, w):
        self.show_candidates = w.get_active()
        
    def plot_scroll(self, widget, event):
        # event.button, event.x, event.y
        x = event.x; y = event.y
        if event.direction == gtk.gdk.SCROLL_UP:
            #delta = 0.9
            self.plot_zoomlevel += 1.0
        elif event.direction == gtk.gdk.SCROLL_DOWN:
            #delta = 1.1
            self.plot_zoomlevel -= 1.0

        self.plot_panzoom()
        
##         x1, x2 = self.w.ax.get_xlim()
##         y1, y2 = self.w.ax.get_ylim()
##         self.w.ax.set_xlim(x1*delta, x2*delta)
##         self.w.ax.set_ylim(y1*delta, y2*delta)
##         self.w.canvas.draw()
        
    def pan_plot(self, xdelta, ydelta):
        x1, x2 = self.w.ax.get_xlim()
        y1, y2 = self.w.ax.get_ylim()
        
        self.w.ax.set_xlim(x1+xdelta, x2+xdelta)
        self.w.ax.set_ylim(y1+ydelta, y2+ydelta)
        self.w.canvas.draw()
        
    def plot_button_press(self, widget, event):
        # event.button, event.x, event.y
        x = event.x; y = event.y
        button = 0
        if event.button != 0:
            button |= 0x1 << (event.button - 1)
        self.logger.debug("button event at %dx%d, button=%x" % (x, y, button))

        self.plot_x, self.plot_y = x, y
        return True

    def plot_button_release(self, widget, event):
        # event.button, event.x, event.y
        x = event.x; y = event.y
        button = 0
        if event.button != 0:
            button |= 0x1 << (event.button - 1)
        self.logger.debug("button release at %dx%d button=%x" % (x, y, button))
            

    def plot_motion_notify(self, widget, event):
        button = 0
        if event.is_hint:
            x, y, state = event.window.get_pointer()
        else:
            x, y, state = event.x, event.y, event.state
        
        if state & gtk.gdk.BUTTON1_MASK:
            button |= 0x1
        elif state & gtk.gdk.BUTTON2_MASK:
            button |= 0x2
        elif state & gtk.gdk.BUTTON3_MASK:
            button |= 0x4
        # self.logger.debug("motion event at %dx%d, button=%x" % (x, y, button))

        if button & 0x1:
            xdelta = x - self.plot_x
            ydelta = y - self.plot_y
            self.pan_plot(xdelta, ydelta)
            

    def __str__(self):
        return 'pick'
    
#END