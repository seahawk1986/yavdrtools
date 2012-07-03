yavdrtools
==========

XBMC Addon to integrate XBMC-Powersafe timeout and VDR activities. Only works with recent versions of dbus2vdr as in yaVDR 0.5

Needs vdr-plugin-dbus2vdr version 20120627202029unstable-0yavdr0~precise or higher: https://launchpad.net/~yavdr/+archive/unstable-vdr/+sourcepub/2534357/+listing-archive-extra

Copy 30_script to /etc/yavdr/templates_custom/etc/init/xbmc-exit.conf/30_script and recreate the file from templates:
sudo process-template /etc/init/xbmc-exit.conf

Copy S92.xbmcactivity to /usr/share/vdr/shutdown-hooks/ and deactivate XBMC Option in yaVDR Webfrontend in the lifeguard-addon settings

If XBMC is set as default frontend, replaceaction for <power> in your remote.xml with this call:
<power>XBMC.RunScript(service.vdr.yavdr-tools,"check")</power>
