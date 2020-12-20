from __future__ import print_function
# for localized messages
from . import _

from Screens.Screen import Screen
from Plugins.Plugin import PluginDescriptor
from Components.Label import Label
from Components.ActionMap import ActionMap
from Components.Sources.StaticText import StaticText
from Components.NimManager import nimmanager
from Components.config import config, configfile, ConfigSubsection, ConfigSelection, ConfigYesNo, ConfigInteger, getConfigListEntry
from Components.ConfigList import ConfigListScreen
from Screens.MessageBox import MessageBox
from Screens.ServiceScan import ServiceScan

from Tools.BoundFunction import boundFunction

from enigma import eComponentScan

from .TerrestrialScan import TerrestrialScan, setParams
from .MakeBouquet import MakeBouquet

import os

config.plugins.TerrestrialScan = ConfigSubsection()
config.plugins.TerrestrialScan.networkid_bool = ConfigYesNo(default = False)
config.plugins.TerrestrialScan.networkid = ConfigInteger(default = 0, limits = (0, 65535))
config.plugins.TerrestrialScan.clearallservices = ConfigYesNo(default = True)
config.plugins.TerrestrialScan.onlyfree = ConfigYesNo(default = True)
uhf_vhf_choices = [
			('uhf', _("UHF Europe")),
			('uhf_vhf', _("UHF/VHF Europe")),
			('australia', _("Australia generic"))]
if nimmanager.getTerrestrialsList(): # check transponders are available from terrestrial.xml
	uhf_vhf_choices.append(('xml', _("From XML")))
config.plugins.TerrestrialScan.uhf_vhf = ConfigSelection(default = 'uhf', choices = uhf_vhf_choices)
config.plugins.TerrestrialScan.makebouquet = ConfigYesNo(default = True)
config.plugins.TerrestrialScan.makeradiobouquet = ConfigYesNo(default = False)
config.plugins.TerrestrialScan.makexmlfile = ConfigYesNo(default = False)
config.plugins.TerrestrialScan.lcndescriptor = ConfigSelection(default = 0x83, choices = [
			(0x83, "0x83"),
			(0x87, "0x87")])
config.plugins.TerrestrialScan.channel_list_id = ConfigInteger(default = 0, limits = (0, 65535))
config.plugins.TerrestrialScan.stabliseTime = ConfigSelection(default = 2, choices = [(i, "%d" % i) for i in range(2, 11)])

class TerrestrialScanScreen(ConfigListScreen, Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		self.setup_title = _('Terrestrial Scan')
		Screen.setTitle(self, self.setup_title)
		self.skinName = ["TerrestrialScanScreen", "Setup"]
		self.onChangedEntry = []
		self.session = session
		ConfigListScreen.__init__(self, [], session = session, on_change = self.changedEntry)

		self["actions2"] = ActionMap(["SetupActions"],
		{
			"menu": self.keyCancel,
			"cancel": self.keyCancel,
			"save": self.keyGo,
		}, -2)

		self["key_red"] = StaticText(_("Exit"))
		self["key_green"] = StaticText(_("Scan"))

		self["description"] = Label("")

		self.transponders_unique = {}
		self.session.postScanService = self.session.nav.getCurrentlyPlayingServiceOrGroup()

		self.dvbt_capable_nims = []
		for nim in nimmanager.nim_slots:
			if self.config_mode(nim) != "nothing":
				if nim.isCompatible("DVB-T") or (nim.isCompatible("DVB-S") and nim.canBeCompatible("DVB-T")):
					self.dvbt_capable_nims.append(nim.slot)

		nim_list = []
		nim_list.append((-1, _("Automatic")))
		for x in self.dvbt_capable_nims:
			nim_list.append((nimmanager.nim_slots[x].slot, nimmanager.nim_slots[x].friendly_full_description))
		self.scan_nims = ConfigSelection(choices = nim_list)

		self.createSetup()

		if not self.selectionChanged in self["config"].onSelectionChanged:
			self["config"].onSelectionChanged.append(self.selectionChanged)
		self.selectionChanged()

	def createSetup(self):
		self.indent = "- "
		setup_list = []
		setup_list.append(getConfigListEntry(_("Tuner"), self.scan_nims, _('Select a tuner that is configured for terrestrial scans. "Automatic" will pick the highest spec available tuner.')))
		setup_list.append(getConfigListEntry(_("Bandplan"), config.plugins.TerrestrialScan.uhf_vhf, _('Most transmitters in European countries only have TV channels in the UHF band. Select "From XML" to access bandplans that are preloaded on the device.')))

		if config.plugins.TerrestrialScan.uhf_vhf.value == "xml":
			self.setTerrestrialLocationEntries()
			setup_list.append(self.terrestrialCountriesEntry)
			setup_list.append(self.terrestrialRegionsEntry)
		
		setup_list.append(getConfigListEntry(_("Clear before scan"), config.plugins.TerrestrialScan.clearallservices, _('If you select "yes" all stored terrestrial channels will be deleted before starting the current search.')))
		setup_list.append(getConfigListEntry(_("Only free scan"), config.plugins.TerrestrialScan.onlyfree, _('If you select "yes" the scan will only save channels that are not encrypted; "no" will find encrypted and non-encrypted channels.')))
		setup_list.append(getConfigListEntry(_('Restrict search to single ONID'), config.plugins.TerrestrialScan.networkid_bool, _('Select "Yes" to restrict the search to multiplexes that belong to a single original network ID (ONID). Select "No" to search all ONIDs.')))

		if config.plugins.TerrestrialScan.networkid_bool.value:
			setup_list.append(getConfigListEntry(self.indent + _('ONID to search'), config.plugins.TerrestrialScan.networkid, _('Enter the original network ID (ONID) of the multiplexes you wish to restrict the search to. UK terrestrial television normally ONID "9018".')))

		setup_list.append(getConfigListEntry(_("Create terrestrial bouquet"), config.plugins.TerrestrialScan.makebouquet, _('If you select "yes" and LCNs are found in the NIT, the scan will create a bouquet of terrestrial channels in LCN order and add it to the bouquet list.')))
		if config.plugins.TerrestrialScan.makebouquet.value:
			setup_list.append(getConfigListEntry(self.indent + _("Create separate radio bouquet"), config.plugins.TerrestrialScan.makeradiobouquet, _('If you select "yes" and radio services are fond these will be place in a separate bouquet. Otherwise TV and radio services will be placed in a combined bouquet.')))
			setup_list.append(getConfigListEntry(self.indent + _("LCN Descriptor"), config.plugins.TerrestrialScan.lcndescriptor, _('Select the LCN descriptor used in your area. 0x83 is the default DVB standard descriptor. 0x87 is used in some Scandinavian countries.')))
			if config.plugins.TerrestrialScan.lcndescriptor.value == 0x87:
				setup_list.append(getConfigListEntry(self.indent + self.indent + _("Channel list ID"), config.plugins.TerrestrialScan.channel_list_id, _('Enter channel list ID used in your area. If you are not sure enter zero.')))

		if config.plugins.TerrestrialScan.uhf_vhf.value != "xml":
			setup_list.append(getConfigListEntry(_("Create terrestrial.xml file"), config.plugins.TerrestrialScan.makexmlfile, _('Select "yes" to create a custom terrestrial.xml file and install it in /etc/enigma2 for system scans to use.')))
		setup_list.append(getConfigListEntry(_("Signal quality stabisation time (secs)"), config.plugins.TerrestrialScan.stabliseTime, _('Period of time to wait for the tuner to stabalise before taking a signal quality reading. 2 seconds is good for most hardware but some may require longer.')))

		self["config"].list = setup_list
		self["config"].l.setList(setup_list)

	def setTerrestrialLocationEntries(self):
		slotid = self.dvbt_capable_nims[0] if self.scan_nims.value < 0 else self.scan_nims.value # number of first enabled terrestrial tuner if automatic is selected.
		nimConfig = nimmanager.nim_slots[slotid].config

		# country
		if not hasattr(self, "terrestrialCountriesEntry"):
			terrestrialcountrycodelist = nimmanager.getTerrestrialsCountrycodeList()
			terrestrialcountrycode = nimmanager.getTerrestrialCountrycode(slotid) # number of first enabled terrestrial tuner if automatic is selected.
			default = terrestrialcountrycode in terrestrialcountrycodelist and terrestrialcountrycode or None
			choices = [("all", _("All"))]+sorted([(x, self.countrycodeToCountry(x)) for x in terrestrialcountrycodelist], key=lambda listItem: listItem[1])
			self.terrestrialCountries = ConfigSelection(default = default, choices = choices)
			self.terrestrialCountriesEntry = getConfigListEntry(self.indent + _("Country"), self.terrestrialCountries, _("Select your country. If not available select 'all'."))

		# region
		if self.terrestrialCountries.value == "all":
			terrstrialNames = [x[0] for x in sorted(sorted(nimmanager.getTerrestrialsList(), key=lambda listItem: listItem[0]), key=lambda listItem: self.countrycodeToCountry(listItem[2]))]
		else:
			terrstrialNames = sorted([x[0] for x in nimmanager.getTerrestrialsByCountrycode(self.terrestrialCountries.value)])
		default = nimConfig.terrestrial.value in terrstrialNames and nimConfig.terrestrial.value or None
		self.terrestrialRegions = ConfigSelection(default = default, choices = terrstrialNames)
		self.terrestrialRegionsEntry = getConfigListEntry(self.indent + _("Region"), self.terrestrialRegions, _("Select your region. If not available change 'Country' to 'all' and select one of the default alternatives."))

	def countrycodeToCountry(self, cc):
		if not hasattr(self, 'countrycodes'):
			self.countrycodes = {}
			from Tools.CountryCodes import ISO3166
			for country in ISO3166:
				self.countrycodes[country[2]] = country[0]
		if cc.upper() in self.countrycodes:
			return self.countrycodes[cc.upper()]
		return cc

	def selectionChanged(self):
		self["description"].setText(self["config"].getCurrent()[2])

	# for summary:
	def changedEntry(self):
		for x in self.onChangedEntry:
			x()

	def getCurrentEntry(self):
		return self["config"].getCurrent()[0]

	def getCurrentValue(self):
		return str(self["config"].getCurrent()[1].getText())

	def createSummary(self):
		from Screens.Setup import SetupSummary
		return SetupSummary

	def keyGo(self):
#		config.plugins.TerrestrialScan.save()
		for x in self["config"].list:
			x[1].save()
		configfile.save()
		self.startScan()

	def startScan(self):
		args = {"feid": int(self.scan_nims.value), "uhf_vhf": config.plugins.TerrestrialScan.uhf_vhf.value, "networkid": int(config.plugins.TerrestrialScan.networkid.value), "restrict_to_networkid": config.plugins.TerrestrialScan.networkid_bool.value, "stabliseTime": config.plugins.TerrestrialScan.stabliseTime.value}
		if config.plugins.TerrestrialScan.uhf_vhf.value == "xml":
			args["region"] = self.terrestrialRegions.value
		self.session.openWithCallback(self.terrestrialScanCallback, TerrestrialScan, args)

	def keyCancel(self):
		if self["config"].isChanged():
			self.session.openWithCallback(self.cancelCallback, MessageBox, _("Really close without saving settings?"))
		else:
			self.cancelCallback(True)

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
		self.newConfig()

	def keyRight(self):
		ConfigListScreen.keyRight(self)
		self.newConfig()

	def newConfig(self):
		cur = self["config"].getCurrent()
		if len(cur)>1:
			if cur[1] in (config.plugins.TerrestrialScan.uhf_vhf, getattr(self, "terrestrialCountries", None), config.plugins.TerrestrialScan.networkid_bool, config.plugins.TerrestrialScan.makebouquet, config.plugins.TerrestrialScan.lcndescriptor):
				self.createSetup()

	def cancelCallback(self, answer):
		if answer:
			for x in self["config"].list:
				x[1].cancel()
			self.close(False)

	def terrestrialScanCallback(self, answer=None):
		print("answer", answer)
		if answer:
			self.feid = answer[0]
			self.transponders_unique = answer[1]
			if config.plugins.TerrestrialScan.makebouquet.value or config.plugins.TerrestrialScan.makexmlfile.value:
				self.session.openWithCallback(self.MakeBouquetCallback, MakeBouquet, {"feid": self.feid, "transponders_unique": self.transponders_unique, "FTA_only": config.plugins.TerrestrialScan.onlyfree.value, "makebouquet": config.plugins.TerrestrialScan.makebouquet.value, "makexmlfile": config.plugins.TerrestrialScan.makexmlfile.value, "lcndescriptor": config.plugins.TerrestrialScan.lcndescriptor.value, "channel_list_id": config.plugins.TerrestrialScan.channel_list_id.value})
			else:
				self.doServiceSearch()
		else:
			self.session.nav.playService(self.session.postScanService)

	def MakeBouquetCallback(self, answer=None):
		print("answer", answer)
		if answer:
			self.feid = answer[0]
			self.transponders_unique = answer[1]
			self.doServiceSearch()
		else:
			self.session.nav.playService(self.session.postScanService)

	def doServiceSearch(self):
		tlist = []
		for transponder in self.transponders_unique:
			tlist.append(setParams(self.transponders_unique[transponder]["frequency"], self.transponders_unique[transponder]["system"], self.transponders_unique[transponder]["bandwidth"]))
		self.startServiceSearch(tlist, self.feid)

	def startServiceSearch(self, tlist, feid):
		flags = 0
		if config.plugins.TerrestrialScan.clearallservices.value:
			flags |= eComponentScan.scanRemoveServices
		else:
			flags |= eComponentScan.scanDontRemoveUnscanned
		if config.plugins.TerrestrialScan.onlyfree.value:
			flags |= eComponentScan.scanOnlyFree
		networkid = 0
		self.session.openWithCallback(self.startServiceSearchCallback, ServiceScan, [{"transponders": tlist, "feid": feid, "flags": flags, "networkid": networkid}])

	def startServiceSearchCallback(self, answer=None):
		self.session.nav.playService(self.session.postScanService)
		if answer:
			self.close(True)

	def config_mode(self, nim): # Workaround for OpenATV > 5.3
		try:
			return nim.config_mode
		except AttributeError:
			return nim.isCompatible("DVB-T") and nim.config_mode_dvbt or "nothing"


def TerrestrialScanStart(menuid, **kwargs):
	if menuid == "scan":
		return [(_("Terrestrial Scan"), TerrestrialScanMain, "TerrestrialScanScreen", 75, True)]
	return []

def TerrestrialScanMain(session, close=None, **kwargs):
	session.openWithCallback(boundFunction(TerrestrialScanCallback, close), TerrestrialScanScreen)

def TerrestrialScanCallback(close, answer):
	if close and answer:
		close(True)

def Plugins(**kwargs):
	pList = []
	if nimmanager.hasNimType("DVB-T"):
		pList.append( PluginDescriptor(name=_("Terrestrial Scan"), description="For scanning terrestrial tv", where = PluginDescriptor.WHERE_MENU, needsRestart = False, fnc=TerrestrialScanStart) )
	else:
		print("[TerrestrialScan] No DVB-T tuner available so don't load")
	return pList
