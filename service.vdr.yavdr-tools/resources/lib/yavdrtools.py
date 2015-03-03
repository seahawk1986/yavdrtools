#-*- coding:utf-8 -*-
import sys, os, socket, time
import xbmc, xbmcaddon, xbmcgui, xbmcplugin
import dbus, subprocess

Addon = xbmcaddon.Addon(id="service.vdr.yavdrtools")
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
        # all options within this dict will be synced to VDR
        # important: id within settings.xml must match variable name in vdr's setup.conf
        # Be sure to send the datatypes needed by the dbus2vdr plugin for each setting
        # each dict entry needs this sytax:
        # '<Variable Name>':'<dbus data types ('si'=string, integer; 'ss'=string, string>')>'
        self.Options = {
        'MinUserInactivity':'si',
        'MinEventTimeout':'si',
        'MarginStart':'si',
        'MarginStop':'si',
        'DefaultPriority':'si',
        'MaxVideoFileSize':'si',
        'DefaultLifetime':'si',
        'EPGScanTimeout':'si',
        'SetSystemTime':'si',
        'DiSEqC':'si',
        'EmergencyExit':'si'
        }
        self.getSettings()
        self.debug("yavdr-tools started")
        # get VDR setup vars
        self.getVDRSettings()

        with open('/tmp/shutdownrequest','w') as f:
                        f.write("0")
        # Check if Addon called by RunScript(script[,args]*)
        try:
            if sys.argv[1] == "check":
                self.debug("External Shutdown Request")
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
            self.debug("no sys.arg[1] found - Addon was started by XBMC")
        self.updateXBMCSettings()

        self._manualStart = self.ask_vdrshutdown.ManualStart()
        self.debug("Manual Start: %s"%( self._manualStart))

        while (not xbmc.abortRequested):
            if (self._manualStart == False and
                self.settings['MinEventTimeout'] > 0
                ) or self._exitrequested == 1:
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
                if self.settings['MinUserInactivity'] > 0:
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
                else:
                    xbmc.sleep(self._sleep_interval)

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
        #self.settings['MinUserInactivity'] = int(Addon.getSetting('MinUserInactivity'))*60
        #self.settings['MinEventTimeout'] = int(Addon.getSetting('MinEventTimeout'))*60
        self.settings['active'] = Addon.getSetting('enable_timeout')
        self.settings['notifications'] = Addon.getSetting('enable_notifications')
        self.settings['debug'] = Addon.getSetting('enable_debug')
        for i in self.Options:
            if self.Options[i] == "si":
                if Addon.getSetting(i) in ["false","true"]:
                    self.settings[i] = int(bool(eval(Addon.getSetting(i).capitalize())))
                else:
                    self.settings[i] = int(Addon.getSetting(i))
            else:
                if Addon.getSetting(i) in ["false","true"]:
                    self.settings[i] = int(bool(eval(Addon.getSetting(i).capitalize())))
                else:
                    self.settings[i] = Addon.getSetting(i)
            self.debug("XBMC-Settings %s: %s"%(i,self.settings[i]))
        self.settings['MinUserInactivity'] = self.settings['MinUserInactivity']*60

    def updateVDRSettings(self):
        for i in self.Options:
            #if self.Options[i] == 'si':
                #self.debug("checking %s"%i)
            if i == "MinUserInactivity" or i == "overrun":
                # needed because those values are handled in seconds within this script
                if int(self.settings[i])/60 != getattr(self,i):
                    val = int(self.settings[i])/60
                    self.setVDRSetting(i, val, self.Options[i])
                    self.debug("changed %s to %s"%(i,int(self.settings['MinUserInactivity'])/60))
                    self.MinUserInactivity = int(self.settings[i])/60
                    changed = True
            else:
                if int(self.settings[i]) != getattr(self,i):
                    if self.Options[i] == 'si':
                        self.setVDRSetting(i, int(self.settings[i]), sig=self.Options[i])
                    elif self.Options[i] == 'ss':
                        print "setting %s to %s, signature=%s"%(i,self.settings[i],self.Options[i])
                        self.setVDRSetting(i, self.settings[i], sig=self.Options[i])
                    self.debug("changed %s to %s"%(i,self.settings[i]))
                    changed = True
            #if self.Options[i] == 'ss':
            #    pass

        try:
            if changed:
                # Update VDR settings
                self.getVDRSettings()
        except: pass

    def updateXBMCSettings(self):
        for i in self.Options:
            if i == 'MinUserInactivity':
                if self.settings['MinUserInactivity']/60 !=  self.MinUserInactivity:
                    try:
                        Addon.setSetting(id="MinUserInactivity", value=str(self.MinUserInactivity))
                    except:
                        xbmc.executebuiltin(u"Notification('Error','can't write MinUserInactivity')")
            else:
                if self.settings[i] != getattr(self,i):
                    self.debug("Value for %s in VDR does not match value in XBMC, setting XBMC to VDR's value"%(i))
                    try:
                    	if Addon.getSetting(i) in ["false","true"]:
                    	    state = str(bool(getattr(self,i))).lower()
                    	    print "setting %s to %s"%(i,state)
                            Addon.setSetting(id=i,value=str(state))
                        else:
                            Addon.setSetting(id=i,value=str(getattr(self,i)))
                    except:
                        xbmc.executebuiltin(u"Notification('Error','can't write %s')"%i)

    def getVDRSettings(self):
        self.setupdbus()
        for i in self.Options:
            answer = self.vdrSetupValue.Get(i)

            #value, code, message = self.vdrSetupValue.Get(i)
            setattr(self,i,answer[0])
            self.debug("%s: %s"%(i, answer[0]))

    def setupdbus(self):
        error = True
        while error == True:
            try:
                self.bus = dbus.SystemBus()
                self.shutdownproxy = self.bus.get_object("de.tvdr.vdr","/Shutdown")
                self.setupproxy = self.bus.get_object("de.tvdr.vdr","/Setup")
                self.ask_vdrshutdown = dbus.Interface(self.shutdownproxy,"de.tvdr.vdr.shutdown")
                self.vdrSetupValue = dbus.Interface(self.setupproxy,"de.tvdr.vdr.setup")
                error = False
            except:
                self.debug("could not connect to dbus object of vdr, sleep for 10s")
                xbmc.sleep(10000)
                error = True
        return True

    def setVDRSetting(self, setting, value, sig):
        """Set VDR setting via dbus. Needs setting name, setting value and datatypes"""
        print "received signature %s"%sig
        try:
            if sig == 'si':
        	    answer = unicode(self.vdrSetupValue.Set(dbus.String(setting), dbus.Int32(value), signature=sig))
    	    elif sig == 'ss':
    	        answer = unicode(self.vdrSetupValue.Set(dbus.String(setting), dbus.String(value), signature=sig))
        except:
            self.xbmcNotify(title="dbus connection broken",message="will try to reconnect in 10s")
            self.setupdbus()
        finally:
            if sig == 'si':
        	    answer = unicode(self.vdrSetupValue.Set(dbus.String(setting), dbus.Int32(value), signature=sig))
    	    elif sig == 'ss':
    	        answer = unicode(self.vdrSetupValue.Set(dbus.String(setting), dbus.String(value), signature=sig))

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

