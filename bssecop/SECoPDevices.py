from collections import OrderedDict, namedtuple

from ophyd.status import Status
from ophyd import Kind
from ophyd import BlueskyInterface

from ophyd.v2.core import StandardReadable, AsyncStatus, AsyncReadable, observe_value, Device

from bluesky.protocols import Movable, Stoppable, SyncOrAsync
 
from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Coroutine,
    Dict,
    Generic,
    Iterable,
    List,
    Optional,
    Protocol,
    Sequence,
    Set,
    TypeVar,
    cast,
    runtime_checkable,
)

from bluesky.protocols import (
    Configurable,
    Descriptor,
    HasName,
    Movable,
    Readable,
    Reading,
    Stageable,
    Status,
    Subscribable,
)
 
from bssecop.AsyncSecopClient import AsyncSecopClient
from frappy.logging import logger

from bssecop.SECoPSignal import *

from bssecop.propertykeys import * 

import time
import re
import importlib
import sys

"""_summary_
    
    SECNode
    ||
    ||
    ||---dev1(readable)
    ||---dev2(drivable)
    ||---dev3(writable)
    ||---dev4(readable)
"""




def clean_identifier(anystring):
    return str(re.sub(r'\W+|^(?=\d)', '_', anystring))

def class_from_interface(mod_properties : dict):
        
    for interface_class in mod_properties.get(INTERFACE_CLASSES):
        try:
            return IF_CLASSES[interface_class]
        except KeyError:
            continue
    raise Exception("no compatible Interfaceclass found in: " + str(mod_properties.get(INTERFACE_CLASSES)))

def get_config_attrs(parameters):
    parameters_cfg = parameters.copy()
    parameters_cfg.pop("target", None)
    parameters_cfg.pop("value", None)
    return parameters_cfg







class SECoPReadableDevice(StandardReadable):

    def __init__(
        self,
        secclient: AsyncSecopClient,
        module_name: str
        ):   
    
        
        self._secclient = secclient
        
        module_desc = secclient.modules[module_name]
        
        self.value: SECoPSignalR
        self.status: SECoPSignalR
        
        
        #list for config signals
        config = [] 
        #list for read signals
        read   = []
        
        # generate Signals from Module Properties
        for property in module_desc['properties']:
            setattr(self,property,SECoPPropertySignal(property,module_desc['properties']))
            config.append(getattr(self,property))

        # generate Signals from Module parameters eiter r or rw
        for parameter, properties in module_desc['parameters'].items():
            
            #construct signal
            readonly = properties.get('readonly',None)
            if readonly == True:
                setattr(self,parameter,SECoPSignalR((module_name,parameter),secclient=secclient))
            elif readonly == False:
                setattr(self,parameter,SECoPSignalRW((module_name,parameter),secclient=secclient))
            else:
                raise Exception('Invalid SECoP Parameter, readonly property is mandatory, but was not found, or is not bool')

            # in SECoP only the 'value' parameter is the primary read prameter
            if parameter == 'value':
                read.append(getattr(self,parameter))
            else:
                config.append(getattr(self,parameter))
        
        
        
        #TODO Commands!!!
        
        super().__init__(prefix = None, name=module_name, config = config,read=read)
        
    def set_name(self, name: str = ""):
        #if name and not self._name:
        self._name = name
        for attr_name, attr in self.__dict__.items():
            # TODO: support lists and dicts of devices
            if isinstance(attr, Device):
                attr.set_name(f"{name}-{attr_name.rstrip('_')}")
                attr.parent = self

    
    async def configure(self, d: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Configure the device for something during a run

        This default implementation allows the user to change any of the
        `configuration_attrs`. Subclasses might override this to perform
        additional input validation, cleanup, etc.

        Parameters
        ----------
        d : dict
            The configuration dictionary. To specify the order that
            the changes should be made, use an OrderedDict.

        Returns
        -------
        (old, new) tuple of dictionaries
        Where old and new are pre- and post-configure configuration states.
        """
        old = await self.read_configuration()
        stat = []
        for key, val in d.items():
            if key not in self._conf_signals:
                # a little extra checking for a more specific error msg
                raise ValueError(
                    "%s is not one of the "
                    "configuration_fields, so it cannot be "
                    "changed using configure" % key
                )
            stat.append(getattr(self,key).set(val))
            
        await asyncio.gather(*stat)
        new = self.read_configuration()
        return old, new
    
class SECoPWritableDevice(SECoPReadableDevice,Movable):
    """Fast settable device target"""
    def __init__(self, secclient: AsyncSecopClient, module_name: str):
        super().__init__(secclient, module_name)
        self.target:SECoPSignalRW
        
    def set(self, value) -> AsyncStatus:
        return AsyncStatus(self.target.set(value,False))
    

class SECoPMoveableDevice(SECoPWritableDevice,Movable,Stoppable):
    def __init__(self, secclient: AsyncSecopClient, module_name: str):
        super().__init__(secclient, module_name)
        
        
        self._success = True
        
    def set(self,new_target,timeout: Optional[float] = None) -> AsyncStatus:
        coro = asyncio.wait_for(self._move(new_target), timeout=timeout)
        return AsyncStatus(coro)
    
    async def _move(self,new_target):
        self._success = True
        await self.target.set(new_target,wait=False)
        async for current_stat in observe_value(self.status):
            print(current_stat)
            v = current_stat[0].value
            if 100 <= v  < 300:
                print("done")
                break
        
        if not self._success:
            raise RuntimeError("Module was stopped")
        
    async def stop(self, success=True) -> SyncOrAsync[None]:
        pass
        
    
    
class SECoP_Node_Device(StandardReadable):
    def __init__(
        self,
        secclient: AsyncSecopClient
        ):   
    
        
        self._secclient = secclient
        
        
        self.modules :   Dict[str,T] = self._secclient.modules
        self.Devices : Dict[str,T] = {}
        
       

        
        #Name is set to sec-node equipment_id
        name = self._secclient.properties[EQUIPMENT_ID] 
        
        config = [] 
        
        for property in self._secclient.properties:
            setattr(self,property,SECoPPropertySignal(property,secclient.properties))
            config.append(getattr(self,property))
    
        
        
        for module, module_desc in self._secclient.modules.items():
            SECoPDeviceClass = class_from_interface(module_desc['properties'])
            
            setattr(self,module,SECoPDeviceClass(secclient,module))
            
        super().__init__(prefix = None, name=name, config = config)
        

        
    def set_name(self, name: str = ""):
        #if name and not self._name:
        self._name = name
        for attr_name, attr in self.__dict__.items():
            # TODO: support lists and dicts of devices
            if isinstance(attr, Device):
                attr.set_name(f"{name}-{attr_name.rstrip('_')}")
                attr.parent = self


   
    def init_Devices_from_Description(self):
        
        prefix = self._get_prefix()
        setupInfo = {}
        
        # retrieve Object initialization Data for Devices from the Module Descriptions
        for module , module_description in self._secclient.modules.items():
            # Descriptive Data of Module:
            module_properties = module_description.get('properties', {})
            module_parameters = module_description.get('parameters',{})
         
            # Interfaceclass:
            cls = class_from_interface(module_properties)
            
            
            module_cfg = {}
            module_cfg["name"] = module
            module_cfg["secclient"] = self._secclient
            module_cfg["parent"] = self

            # Split into read attributes
            module_cfg["read_attrs"] = {"value" : module_parameters.get('value', {})}
            # and configuration attributes
            module_cfg["configuration_attrs"] = get_config_attrs(module_parameters)
            
            #TODO kind
            #TODO Prefix
            #TODO module properties

            setupInfo[module] = ('SECoPDevices',cls.__name__, module_cfg)
        
        # Initialize Device objects
        for devname, devcfg in setupInfo.items():  
                       
            devcls = getattr(importlib.import_module(devcfg[0]), devcfg[1])
            dev = devcls(**devcfg[2])
            
            print(devname)
            
            self.Devices[devname] = dev
            self.__setattr__(devname,dev)
            
     


    
IF_CLASSES = {
    'Drivable': SECoPMoveableDevice,
    'Writable': SECoPWritableDevice,
    'Readable': SECoPReadableDevice,
    'Module'  : SECoPReadableDevice
}



ALL_IF_CLASSES = set(IF_CLASSES.values())

# TODO
#FEATURES = {
#    'HasLimits': SecopHasLimits,
#    'HasOffset': SecopHasOffset,
#}