#-*- coding:utf-8 -*-
import sys, os, socket, telnetlib, time
import xbmc, xbmcaddon, xbmcgui, xbmcplugin
import dbus

Addon = xbmcaddon.Addon(id="vdr.yavdrtools")

class Main:
    #_base = sys.argv[0]
    _enum_overrun = [1,2,5,10,15,20]
    _enum_idle= [5,10,15,20,25,30,40,50,60,90,120,180,240,300,360,420,480,540,600]
    _sleep_interval = 10000
    _counter = 0
    _idleTime = 0
    _lastIdleTime = 0
    _realIdleTime = 0
    _lastPlaying = False
    _isPlaying = False
    _notifications = False
    _active = False

    # main routine
    def __init__(self):
        #self.debug("Plugin started")
        self.getSettings()
        #for element in  dir(xbmc):
        #    print element
        with open("/tmp/xbmc-shutdown","w") as shutdown:
            shutdown.write("0")
        with open("/tmp/xbmc-active","w") as active:
            active.write("1")
        # main loop
        while (not xbmc.abortRequested):
            self.getSettings()
            if self._counter > 4:
                self._counter = 0
            else:
                self._counter += 1
            # time warp calculations demands to have our own idle timers
            self._lastIdleTime = self._idleTime
            self.debug("lastIdleTime = %s"%self._lastIdleTime)
            self._idleTime = xbmc.getGlobalIdleTime()
            if (self._idleTime > self._lastIdleTime):
                self._realIdleTime = self._realIdleTime + (self._idleTime - self._lastIdleTime)
            else:
                self._realIdleTime = self._idleTime

            # notice changes in playback
            self._lastPlaying = self._isPlaying
            self._isPlaying = xbmc.Player().isPlaying()
            
            # now this one is tricky: a playback ended, idle would suggest to powersave, but we set the clock back for overrun. 
            # Otherwise xbmc could sleep instantly at the end of a movie
            if (self._lastPlaying  == True) & (self._isPlaying == False) & (self._realIdleTime >= self.settings['vdrps_sleepmode_after']):
                self._realIdleTime = self.settings['vdrps_sleepmode_after'] - self.settings['vdrps_overrun']
                #print "vdr.powersave: playback stopped!"
                if self.settings['notifications'] == "true":
                  xbmc.executebuiltin(u"Notification('Inactivity timeout','press key to abort')")
            # powersave checks ...
            self.debug(self._counter)
            vdridle = self.getVDRidle()
            if (self._realIdleTime + 120 >= self.settings['vdrps_sleepmode_after']) and self._counter == 9 and self._isPlaying == False and vdridle:
              if self.settings['notifications'] == "true":
                xbmc.executebuiltin(u"Notification('Inactivity timeout in %s seconds','press key to abort')"%(int(self.settings['vdrps_sleepmode_after']) - int(self._realIdleTime)))
            if (self._realIdleTime >= self.settings['vdrps_sleepmode_after']) and self.settings['active'] == "true":
                self.debug("powersafe-check")
                with open("/tmp/xbmc-active","w") as active:
                        active.write("1")
                # sleeping time already?
                if (self._isPlaying):
                    self.debug("powersave postponed - xbmc is playing ...")
                    with open("/tmp/xbmc-active","w") as active:
                        active.write("1")
                else:
                    with open("/tmp/xbmc-active","w") as active:
                        active.write("0")
                    self.debug("ask if VDR is ready to shutdown")
                    if vdridle:
                        with open("/tmp/xbmc-shutdown","w") as shutdown:
                            shutdown.write("1")
                        xbmc.executebuiltin('Quit')
                    else:
                        with open("/tmp/xbmc-shutdown","w") as shutdown:
                            shutdown.write("0")
            else:
                with open("/tmp/xbmc-active","w") as active:
                        active.write("1")
                with open("/tmp/xbmc-shutdown","w") as shutdown:
                        shutdown.write("0")             
            # sleep a little ...
            xbmc.sleep(self._sleep_interval)

        self.debug("vdr.yavdrtools: Plugin exited")
        exit()
        
        
    # get settings from xbmc
    def getSettings(self):
        self.settings = {}
        self.settings['vdrps_overrun'] = self._enum_overrun[int(Addon.getSetting('vdrps_overrun'))] * 60
        self.settings['vdrps_sleepmode_after'] = self._enum_idle[int(Addon.getSetting('vdrps_sleepmode_after'))] * 60
        self.settings['active'] = Addon.getSetting('enable_timeout')
        self.settings['notifications'] = Addon.getSetting('enable_notifications')
        self.settings['debug'] = Addon.getSetting('enable_debug')


    def debug(self, message):
        if self.settings['debug'] == "true":
            print "debug vdr.yavdrtools: %s"%(message)

            
    def getVDRidle(self, mode=True):
        self.bus = dbus.SystemBus()
        self.proxy = self.bus.get_object("de.tvdr.vdr","/Shutdown")
        self.msgproxy =  self.bus.get_object("de.tvdr.vdr","/Skin")
        self.send_message = dbus.Interface(self.msgproxy, "de.tvdr.vdr.skin")
        #/Skin skin.QueueMessage string:'message text'
        self.ask_vdridle = dbus.Interface(self.proxy,"de.tvdr.vdr.shutdown")
        status, message, code, msg = self.ask_vdridle.ConfirmShutdown(mode)
        if int(status) in [250,990]:
            self._VDRisidle = True
            self.debug("VDR ready to shutdown")
            return True
        else:
            #xbmc.executebuiltin("Notification('yaVDR Tools',%s)"%(message))
            self.send_message.QueueMessage(message)
            self.debug("VDR not ready to shutdown")
            self.debug("got answer: %s: %s"%(status, message))
            if int(status) == 903:
                self.debug("VDR is recording")
                self._isRecording = True
            elif int(status) == 904:
                self.debug("VDR recording is pending")
            elif int(status) in [905,906]:
                self.debug("VDR plugin is active")
            return False
            
