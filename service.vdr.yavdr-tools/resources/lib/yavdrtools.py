﻿#-*- coding:utf-8 -*-
import sys, os, socket, time
import xbmc, xbmcaddon, xbmcgui, xbmcplugin
import dbus, subprocess

Addon = xbmcaddon.Addon(id="vdr.yavdrtools")
gls = Addon.getLocalizedString

class Main:
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
    _manualStart = False
    _xbmcStatus = 1
    _xbmcShutdown = 0

    # main routine
    def __init__(self):
        self.getSettings()
        self.debug("Plugin started")
        # define dbus2vdr communication elements
        self.bus = dbus.SystemBus()
        self.shutdownproxy = self.bus.get_object("de.tvdr.vdr","/Shutdown")
        self.msgproxy =  self.bus.get_object("de.tvdr.vdr","/Skin")
        self.setupproxy = self.bus.get_object("de.tvdr.vdr","/Setup")
        self.send_message = dbus.Interface(self.msgproxy, "de.tvdr.vdr.skin")
        self.ask_vdrshutdown = dbus.Interface(self.shutdownproxy,"de.tvdr.vdr.shutdown")
        self.vdrSetupValue = dbus.Interface(self.setupproxy,"de.tvdr.vdr.setup")
        # get inactivity timeouts
        self.MinUserInactivity, max, message = self.vdrSetupValue.Get('MinUserInactivity')
        self.MinEventTimeout, max, message = self.vdrSetupValue.Get('MinEventTimeout')
        print "VDR UserInactivity:", int(self.MinUserInactivity)
        print "XBMC UserInactivity:", int(self.settings['MinUserInactivity'])/60
        if self.settings['MinUserInactivity']/60 !=  self.MinUserInactivity:
            try:
                Addon.setSetting(id="MinUserInactivity", value=str(self.MinUserInactivity))
            except:
                xbmc.executebuiltin(u"Notification('Error','can't write MinUserInactivity')") 
        if self.settings['MinEventTimeout']/60 != self.MinEventTimeout:
            try:
                Addon.setSetting(id="MinEventTimeout", value=str(self.MinEventTimeout))
            except:
                xbmc.executebuiltin(u"Notification('Error','can't write MinEventTimeout')")
        self._manualStart = self.ask_vdrshutdown.ManualStart()
        if not self._manualStart:
            while not (self._isPlaying or self._lastIdleTime < self._IdleTime()):
                xbmc.sleep(self._sleep_interval)
                self.xbmcShutdown(1)
                self.xbmcStatus(0)
                self._lastIdleTime = self._idleTime
                self._idleTime = xbmc.getGlobalIdleTime()
                self.idleCheck(0)
                xbmc.sleep(self._sleep_interval*6)
        
        self.xbmcShutdown(0)
        self.xbmcStatus(1)
        # main loop
        while (not xbmc.abortRequested):
            self.getSettings()
            self.updateVDRSettings()
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
            if (self._lastPlaying  == True) & (self._isPlaying == False) & (self._realIdleTime >= self.settings['MinUserInactivity']):
                self._realIdleTime = self.settings['MinUserInactivity'] - self.settings['overrun']
                #print "vdr.powersave: playback stopped!"
                if self.settings['notifications'] == "true":
                  xbmc.executebuiltin(u"Notification('Inactivity timeout','press key to abort')")
            # powersave checks ...
            self.debug(self._counter)
            vdridle = self.getVDRidle()
            if (self._realIdleTime + 120 >= self.settings['MinUserInactivity']) and self._counter == 9 and self._isPlaying == False and vdridle:
              if self.settings['notifications'] == "true":
                xbmc.executebuiltin(u"Notification('Inactivity timeout in %s seconds','press key to abort')"%(int(self.settings['MinUserInactivity']) - int(self._realIdleTime)))
            if not self.idleCheck(self.settings['MinUserInactivity']):
                xbmc.sleep(self._sleep_interval)

        self.debug("vdr.yavdrtools: Plugin exit on request")
        exit()
        
    def idleCheck(self, timeout):
        if (self._realIdleTime >= timeout and self.settings['active'] == "true"):
            self.debug("powersafe-check")
            self.xbmcStatus("1")
            # sleeping time already?
            if (self._isPlaying):
                self.debug("powersave postponed - xbmc is playing ...")
                self.xbmcStatus(1)
            else:
                self.xbmcStatus(0)
                self.debug("ask if VDR is ready to shutdown")
                vdridle = self.getVDRidle()
                if vdridle:
                    self.xbmcShutdown(1)
                    xbmc.executebuiltin('Quit')
                else:
                    self.xbmcShutdown(0)
            
        else:
            self.xbmcStatus(1)
            self.xbmcShutdown(0)
        if self._xbmcStatus == 0 and self._xbmcShutdown == 1:
            exit()
            return True
        else:
            return False
    
    def getSettings(self):
        '''get settings from xbmc'''
        self.settings = {}
        self.settings['overrun'] = self._enum_overrun[int(Addon.getSetting('overrun'))] * 60
        self.settings['MinUserInactivity'] = int(Addon.getSetting('MinUserInactivity'))*60
        self.settings['MinEventTimeout'] = int(Addon.getSetting('MinEventTimeout'))*60
        self.settings['active'] = Addon.getSetting('enable_timeout')
        self.settings['notifications'] = Addon.getSetting('enable_notifications')
        self.settings['debug'] = Addon.getSetting('enable_debug')

    def updateVDRSettings(self):
	if int(self.settings['MinUserInactivity'])/60 != self.MinUserInactivity:
            val = int(self.settings['MinUserInactivity'])/60
            #print self.vdrSetupValue(dbus.Int32(value))
            print subprocess.Popen(["/usr/bin/vdr-dbus-send", "/Setup", "setup.Set", 'string:MinUserInactivity', 'int32:%s'%(val)])
            self.debug("changed MinUserInactivity to %s"%(int(self.settings['MinUserInactivity'])/60))
            self.MinUserInactivity = int(self.settings['MinUserInactivity'])/60
        if int(self.settings['MinEventTimeout'])/60 != self.MinEventTimeout:
            aval = int(self.settings['MinEventTimeout'])/60
            #self.vdrSetupValue.Set('MinEventTimeout', (dbus.Int32(self.settings['MinEventTimeout'])/60))
            print subprocess.Popen(["/usr/bin/vdr-dbus-send", "/Setup", "setup.Set", 'string:MinEventTimeout', 'int32:%s'%(aval)])
            self.debug("changed MinEventTimeout to %s"%(int(self.settings['MinEventTimeout']/60)))
            self.MinEventTimeout = int(self.settings['MinEventTimeout'])/60

    def debug(self, message):
        '''write debug messages to xbmc.log'''
        if self.settings['debug'] == "true":
            print "debug vdr.yavdrtools: %s"%(message)
    
    def xbmcStatus(self, status):
        self._xbmcStatus = status
        with open("/tmp/xbmc-active","w") as active:
                        active.write(unicode(status))
                        
    def xbmcShutdown(self, status):
        self._xbmcShutdown = status
        with open("/tmp/xbmc-shutdown","w") as shutdown:
                        shutdown.write(unicode(status))
            
    def getVDRidle(self, mode=True):
        '''ask if VDR is ready to shutdown via dbus2vdr-plugin'''
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
            
