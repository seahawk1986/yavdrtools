#-*- coding:utf-8 -*-
import sys, os, socket, time
import xbmc, xbmcaddon, xbmcgui, xbmcplugin
import dbus, subprocess

Addon = xbmcaddon.Addon(id="vdr.yavdrtools")
gls = Addon.getLocalizedString

class Main:
    _enum_overrun = [1,2,5,10,15,20]
    _sleep_interval = 10000
    _counter = 0
    _idleTime = 0
    _lastIdleTime = 0
    _realIdleTime = 0
    _lastPlaying = False
    _isPlaying = False
    _manualStart = False
    _xbmcStatus = 1
    _xbmcShutdown = 0
    _exitrequested = 0

    # main routine
    def __init__(self):
        self.getSettings()
        self.debug("Plugin started")
        # define dbus2vdr communication elements
        self.bus = dbus.SystemBus()
        self.shutdownproxy = self.bus.get_object("de.tvdr.vdr","/Shutdown")
        self.setupproxy = self.bus.get_object("de.tvdr.vdr","/Setup")
        self.ask_vdrshutdown = dbus.Interface(self.shutdownproxy,"de.tvdr.vdr.shutdown")
        self.vdrSetupValue = dbus.Interface(self.setupproxy,"de.tvdr.vdr.setup")
        # get inactivity timeouts
        self.MinUserInactivity, max, message = self.vdrSetupValue.Get('MinUserInactivity')
        self.MinEventTimeout, max, message = self.vdrSetupValue.Get('MinEventTimeout')
        self.debug("VDR UserInactivity: %s"%(self.MinUserInactivity))
        self.debug("XBMC UserInactivity: %s"%(int(self.settings['MinUserInactivity'])/60))
        with open('/tmp/shutdownrequest','w') as f:
                        f.write("0") 
        # Check if Addon called by RunScript(script[,args]*)
        try:
            if sys.argv[1] == "check":
                self.xbmcNotify(message="Shutdown requested, probing VDR")
                oldstatus = self.xbmcStatus
                self.xbmcStatus(0)
                idle, message = self.getVDRidle()
                if idle:
                    self.xbmcNotify(message="Shutdown initiated")
                    xbmc.sleep(2000)
                    self.xbmcShutdown(1)
                    xbmc.executebuiltin('Shutdown')
                    exit()
                else:
                    self.xbmcNotify(message=message)
                    xbmc.sleep(2000)
                    self.xbmcNotify(title="Auto shutdown activated", message="Will shutdown ASAP")
                    with open('/tmp/shutdownrequest','w') as f:
                        f.write("1")
                    exit()
        except:
            print "no sys.arg[1] found"

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
        self.debug("Manual Start: %s"%( self._manualStart))
        while (not xbmc.abortRequested):
            if (self._manualStart == False and self.MinEventTimeout > 0) or self._exitrequested == 1:
                self.debug("Mode: Timer start or exit requested")
                self._idleTime = 0
                while not (self._isPlaying):
                    self.debug("trying to shutdown XBMC")
                    self.xbmcShutdown(1)
                    self.xbmcStatus(0)
                    self._lastIdleTime = self._idleTime
                    self._idleTime = xbmc.getGlobalIdleTime()
                    if self._idleTime <= self._lastIdleTime:
                        break
                    self.idleCheck(0)
                    interval = self._sleep_interval
                    self.debug(interval)
                    xbmc.sleep(self._sleep_interval)
                self._exitrequested = 0
                self.xbmcNotify(message="Autoshutdown aborted")
                with open('/tmp/shutdownrequest','w') as f:
                        f.write("0")
            
            self.xbmcShutdown(0)
            self.xbmcStatus(1)
            # main loop+
            while self._exitrequested == 0:
                self.getSettings()
                self.updateVDRSettings()
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
                    self.debug("vdr.powersave: playback stopped!")
                # powersave checks ...
                if (self._realIdleTime + 60 >= self.settings['MinUserInactivity']) and self._isPlaying == False:
                    self.xbmcStatus(0)
                    idle, message = self.getVDRidle()
                    if idle and int(self.settings['MinUserInactivity']) - int(self._realIdleTime) >= 0:
                        self.xbmcNotify('Inactivity timeout in %s seconds'%(int(self.settings['MinUserInactivity']) - int(self._realIdleTime)),'press key to abort')
                    if (self._realIdleTime >= self.settings['MinUserInactivity']):
                	    self.idleCheck(self.settings['MinUserInactivity'])
                    xbmc.sleep(self._sleep_interval/2)
                else:
                    xbmc.sleep(self._sleep_interval)
                with open('/tmp/shutdownrequest','r') as f:
                    #print "EXITREQUESTED = %s"%(bool(f.read()))
                    self._exitrequested = int(f.read())

        self.debug("vdr.yavdrtools: Plugin exit on request")
        exit()
        
    def idleCheck(self, timeout):
        if self.settings['active'] == "true" and self.MinUserInactivity > 0:
            self.debug("powersafe-check, timeout is set to %s"%(timeout))
            # sleeping time already?
            if (self._isPlaying) or (self._realIdleTime <= timeout):
                self.debug("powersave postponed - xbmc is playing ...")
                self.xbmcStatus(1)
                return False
            else:
                self.xbmcStatus(0)
                self.debug("ask if VDR is ready to shutdown")
                vdridle, message = self.getVDRidle()
                if vdridle:
                    self.xbmcShutdown(1)
                    self.xbmcNotify('Point of no return', 'Good Bye')
                    xbmc.executebuiltin('Quit')
                    return True
                else:
                    self.xbmcShutdown(0)
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
            self.setVDRSetting("MinUserInactivity", val)
            self.debug("changed MinUserInactivity to %s"%(int(self.settings['MinUserInactivity'])/60))
            self.MinUserInactivity = int(self.settings['MinUserInactivity'])/60
        if int(self.settings['MinEventTimeout'])/60 != self.MinEventTimeout:
            aval = int(self.settings['MinEventTimeout'])/60
            self.setVDRSetting('MinEventTimeout', aval)
            self.debug("changed MinEventTimeout to %s"%(int(self.settings['MinEventTimeout']/60)))
            self.MinEventTimeout = int(self.settings['MinEventTimeout'])/60
    
    def setVDRSetting(self, setting, value, sig="si"):
        """Set VDR setting via dbus. Needs setting name, setting value and datatypes"""
        answer = unicode(self.vdrSetupValue.Set(dbus.String(setting), dbus.Int32(value), signature=sig))
        self.debug(answer)

    def xbmcNotify(self, title="yaVDR Tools",  message="Test"):
        """Send Notication to User via XBMC"""
        if self.settings['notifications'] == "true":
            xbmc.executebuiltin(u"Notification(%s,%s)"%(title,message))

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
        self.ask_vdridle = dbus.Interface(self.proxy,"de.tvdr.vdr.shutdown")
        status, message, code, msg = self.ask_vdridle.ConfirmShutdown(mode)
        self.debug("VDR returned: %s"%status)
        if int(status) in [250,990]:
            self._VDRisidle = True
            self.debug("VDR ready to shutdown")
            return True, message
        else:
            self.debug("VDR not ready to shutdown")
            self.debug("got answer: %s: %s"%(status, message))
            if int(status) == 903:
                self.debug("VDR is recording")
                self._isRecording = True
            elif int(status) == 904:
                self.debug("VDR recording is pending")
            elif int(status) in [905,906]:
                self.debug("VDR plugin is active")
            return False, message
            
