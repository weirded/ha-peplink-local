# The Peplink Local API

## Authentication

We will POST to the `/api/login` endpoint to authenticate, passing the username and password in the body per this example:

```json
{
    "username": "admin",
    "password": "password",
    "challenge": "challenge"
}
```

> IMPORTANT: We need to use a cookie jar and maintain the cookie for all future calls so the `bauth` cookie is available for all future calls.

### Official API documentation

Documentation: https://download.peplink.com/resources/Peplink-Router-API-Documentation-for-Firmware-8.1.1.pdf

#### APIs used by this integration

##### Reading device information
- /api/status.client -- Get client information for device_tracker

Example response: 
```json
{
  "list": [
    {
      "ip": "192.168.211.2",
      "connectionType": "ethernet",
      "lease": {
        "expiresIn": 53128,
        "type": "dhcp"
      },
      "name": "UDM Pro WAN1",
      "mac": "AA:BB:CC:DD:EE:FF",
      "active": true,
      "vlanId": 100
    },
    {
      "ip": "192.168.212.2",
      "connectionType": "ethernet",
      "lease": {
        "expiresIn": 53228,
        "type": "dhcp"
      },
      "name": "UDM Pro WAN2",
      "mac": "AA:BB:CC:DD:EE:EE",
      "active": true,
      "vlanId": 110
    }
  ],
  "client": [
    {
      "ip": "192.168.211.2",
      "connectionType": "ethernet",
      "lease": {
        "expiresIn": 53128,
        "type": "dhcp"
      },
      "name": "UDM Pro WAN1",
      "mac": "AA:BB:CC:DD:EE:FF",
      "active": true,
      "vlanId": 100
    },
    {
      "ip": "192.168.212.2",
      "connectionType": "ethernet",
      "lease": {
        "expiresIn": 53228,
        "type": "dhcp"
      },
      "name": "UDM Pro WAN2",
      "mac": "AA:BB:CC:DD:EE:EE",
      "active": true,
      "vlanId": 110
    }
  ]
}
```

##### Reading WAN status 

- /api/status.wan.connection -- Get status of WAN connections

Example response: 

```json
{
  "1": {
    "name": "Peak Wifi",
    "enable": true,
    "locked": false,
    "managementOnly": false,
    "ip": "10.10.10.101",
    "statusLed": "green",
    "message": "Connected",
    "uptime": 439609,
    "type": "ethernet",
    "virtualType": "ethernet",
    "virtual": false,
    "priority": 1,
    "portId": 1,
    "dns": [
      "8.8.4.4",
      "1.0.0.1"
    ],
    "mask": 22,
    "gateway": "10.10.10.102",
    "bandwidthAllowanceMonitor": {
      "enable": false,
      "hasSmtp": false
    },
    "method": "staticIp",
    "routingMode": "NAT",
    "mtu": 1500
  },
  "2": {
    "name": "T-Mobile (RM550)",
    "enable": true,
    "locked": false,
    "managementOnly": false,
    "ip": "192.168.1.44",
    "statusLed": "green",
    "message": "Connected",
    "uptime": 440176,
    "type": "ethernet",
    "virtualType": "ethernet",
    "virtual": false,
    "priority": 1,
    "portId": 2,
    "dns": [
      "192.168.1.1"
    ],
    "mask": 24,
    "gateway": "192.168.1.1",
    "bandwidthAllowanceMonitor": {
      "enable": false,
      "hasSmtp": false
    },
    "method": "dhcp",
    "routingMode": "NAT",
    "mtu": 1472
  },
  "3": {
    "name": "T-Mobile (RM520)",
    "enable": true,
    "locked": false,
    "managementOnly": false,
    "ip": "192.168.2.45",
    "statusLed": "green",
    "message": "Connected",
    "uptime": 440093,
    "type": "ethernet",
    "virtualType": "ethernet",
    "virtual": false,
    "priority": 1,
    "portId": 3,
    "dns": [
      "192.168.2.1"
    ],
    "mask": 24,
    "gateway": "192.168.2.1",
    "gatewayUrl": "../../WAN3/Gateway/",
    "bandwidthAllowanceMonitor": {
      "enable": false,
      "hasSmtp": false
    },
    "method": "dhcp",
    "routingMode": "NAT",
    "mtu": 1472
  },
  "4": {
    "name": "WAN 4",
    "enable": false,
    "locked": false,
    "managementOnly": false,
    "statusLed": "gray",
    "message": "Disabled",
    "uptime": 0,
    "type": "ethernet",
    "virtualType": "ethernet",
    "virtual": false,
    "portId": 4,
    "bandwidthAllowanceMonitor": {
      "enable": false,
      "hasSmtp": false
    },
    "method": "dhcp",
    "routingMode": "NAT",
    "mtu": 1440
  },
  "5": {
    "name": "WAN 5",
    "enable": false,
    "locked": false,
    "managementOnly": false,
    "statusLed": "gray",
    "message": "Disabled",
    "uptime": 0,
    "type": "ethernet",
    "virtualType": "ethernet",
    "virtual": false,
    "portId": 5,
    "bandwidthAllowanceMonitor": {
      "enable": false,
      "hasSmtp": false
    },
    "method": "dhcp",
    "routingMode": "NAT",
    "mtu": 1440
  },
  "6": {
    "name": "WAN 6",
    "enable": false,
    "locked": false,
    "managementOnly": false,
    "statusLed": "gray",
    "message": "Disabled",
    "uptime": 0,
    "type": "ethernet",
    "virtualType": "ethernet",
    "virtual": false,
    "portId": 6,
    "bandwidthAllowanceMonitor": {
      "enable": false,
      "hasSmtp": false
    },
    "method": "dhcp",
    "routingMode": "NAT",
    "mtu": 1440
  },
  "7": {
    "name": "WAN 7",
    "enable": false,
    "locked": false,
    "managementOnly": false,
    "statusLed": "gray",
    "message": "Disabled",
    "uptime": 0,
    "type": "ethernet",
    "virtualType": "ethernet",
    "virtual": false,
    "portId": 7,
    "bandwidthAllowanceMonitor": {
      "enable": false,
      "hasSmtp": false
    },
    "method": "dhcp",
    "routingMode": "NAT",
    "mtu": 1440
  },
  "8": {
    "name": "Mobile Internet",
    "enable": false,
    "locked": false,
    "managementOnly": false,
    "statusLed": "gray",
    "message": "Disabled",
    "uptime": 0,
    "type": "modem",
    "virtualType": "modem",
    "virtual": false,
    "portId": 8,
    "bandwidthAllowanceMonitor": {
      "enable": false,
      "hasSmtp": false
    },
    "method": "ppp",
    "routingMode": "NAT",
    "mtu": 1428
  },
  "order": [
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8
  ],
  "supportGatewayProxy": true,
  "connection": [
    {
      "name": "Peak Wifi",
      "enable": true,
      "locked": false,
      "managementOnly": false,
      "ip": "10.10.10.101",
      "statusLed": "green",
      "message": "Connected",
      "uptime": 439609,
      "type": "ethernet",
      "virtualType": "ethernet",
      "virtual": false,
      "priority": 1,
      "portId": 1,
      "dns": [
        "8.8.4.4",
        "1.0.0.1"
      ],
      "mask": 22,
      "gateway": "10.10.10.102",
      "bandwidthAllowanceMonitor": {
        "enable": false,
        "hasSmtp": false
      },
      "method": "staticIp",
      "routingMode": "NAT",
      "mtu": 1500,
      "id": 1
    },
    {
      "name": "T-Mobile (RM550)",
      "enable": true,
      "locked": false,
      "managementOnly": false,
      "ip": "192.168.1.44",
      "statusLed": "green",
      "message": "Connected",
      "uptime": 440176,
      "type": "ethernet",
      "virtualType": "ethernet",
      "virtual": false,
      "priority": 1,
      "portId": 2,
      "dns": [
        "192.168.1.1"
      ],
      "mask": 24,
      "gateway": "192.168.1.1",
      "bandwidthAllowanceMonitor": {
        "enable": false,
        "hasSmtp": false
      },
      "method": "dhcp",
      "routingMode": "NAT",
      "mtu": 1472,
      "id": 2
    },
    {
      "name": "T-Mobile (RM520)",
      "enable": true,
      "locked": false,
      "managementOnly": false,
      "ip": "192.168.2.45",
      "statusLed": "green",
      "message": "Connected",
      "uptime": 440093,
      "type": "ethernet",
      "virtualType": "ethernet",
      "virtual": false,
      "priority": 1,
      "portId": 3,
      "dns": [
        "192.168.2.1"
      ],
      "mask": 24,
      "gateway": "192.168.2.1",
      "gatewayUrl": "../../WAN3/Gateway/",
      "bandwidthAllowanceMonitor": {
        "enable": false,
        "hasSmtp": false
      },
      "method": "dhcp",
      "routingMode": "NAT",
      "mtu": 1472,
      "id": 3
    },
    {
      "name": "WAN 4",
      "enable": false,
      "locked": false,
      "managementOnly": false,
      "statusLed": "gray",
      "message": "Disabled",
      "uptime": 0,
      "type": "ethernet",
      "virtualType": "ethernet",
      "virtual": false,
      "portId": 4,
      "bandwidthAllowanceMonitor": {
        "enable": false,
        "hasSmtp": false
      },
      "method": "dhcp",
      "routingMode": "NAT",
      "mtu": 1440,
      "id": 4
    },
    {
      "name": "WAN 5",
      "enable": false,
      "locked": false,
      "managementOnly": false,
      "statusLed": "gray",
      "message": "Disabled",
      "uptime": 0,
      "type": "ethernet",
      "virtualType": "ethernet",
      "virtual": false,
      "portId": 5,
      "bandwidthAllowanceMonitor": {
        "enable": false,
        "hasSmtp": false
      },
      "method": "dhcp",
      "routingMode": "NAT",
      "mtu": 1440,
      "id": 5
    },
    {
      "name": "WAN 6",
      "enable": false,
      "locked": false,
      "managementOnly": false,
      "statusLed": "gray",
      "message": "Disabled",
      "uptime": 0,
      "type": "ethernet",
      "virtualType": "ethernet",
      "virtual": false,
      "portId": 6,
      "bandwidthAllowanceMonitor": {
        "enable": false,
        "hasSmtp": false
      },
      "method": "dhcp",
      "routingMode": "NAT",
      "mtu": 1440,
      "id": 6
    },
    {
      "name": "WAN 7",
      "enable": false,
      "locked": false,
      "managementOnly": false,
      "statusLed": "gray",
      "message": "Disabled",
      "uptime": 0,
      "type": "ethernet",
      "virtualType": "ethernet",
      "virtual": false,
      "portId": 7,
      "bandwidthAllowanceMonitor": {
        "enable": false,
        "hasSmtp": false
      },
      "method": "dhcp",
      "routingMode": "NAT",
      "mtu": 1440,
      "id": 7
    },
    {
      "name": "Mobile Internet",
      "enable": false,
      "locked": false,
      "managementOnly": false,
      "statusLed": "gray",
      "message": "Disabled",
      "uptime": 0,
      "type": "modem",
      "virtualType": "modem",
      "virtual": false,
      "portId": 8,
      "bandwidthAllowanceMonitor": {
        "enable": false,
        "hasSmtp": false
      },
      "method": "ppp",
      "routingMode": "NAT",
      "mtu": 1428,
      "id": 8
    }
  ]
}
```

### Unofficial APIs 

- Can use same authentication. 
- _ parameter is the current timestamp in milliseconds
- use the same IP, but use /cgi-bin/MANGA/api.cgi?func=<function> instead of /api/<function>

#### Reading traffic 

URL Example: https://10.10.10.1/cgi-bin/MANGA/api.cgi?func=status.traffic&_=1741818098974

Example response: 
```json
{
  "lifetime": {
    "timestamp": 1741038369,
    "datetime": "Mon Mar 03 13:46:09 PST 2025",
    "unit": "MB",
    "all": {
      "overall": {
        "download": 208003,
        "upload": 116122
      }
    },
    "order": [
      "all"
    ]
  },
  "bandwidth": {
    "timestamp": 1741891413,
    "unit": "kbps",
    "1": {
      "name": "Peak Wifi",
      "portType": "ethernet",
      "virtual": false,
      "overall": {
        "download": 2342,
        "upload": 1634
      },
      "details": {
        "http": {
          "download": 178,
          "upload": 8
        },
        "https": {
          "download": 2090,
          "upload": 1562
        },
        "imap": {
          "download": 0,
          "upload": 0
        },
        "pop3": {
          "download": 0,
          "upload": 0
        },
        "smtp": {
          "download": 0,
          "upload": 0
        },
        "others": {
          "download": 73,
          "upload": 63
        }
      }
    },
    "2": {
      "name": "T-Mobile (RM550)",
      "portType": "ethernet",
      "virtual": false,
      "overall": {
        "download": 224,
        "upload": 163
      },
      "details": {
        "http": {
          "download": 117,
          "upload": 7
        },
        "https": {
          "download": 96,
          "upload": 149
        },
        "imap": {
          "download": 0,
          "upload": 0
        },
        "pop3": {
          "download": 0,
          "upload": 0
        },
        "smtp": {
          "download": 0,
          "upload": 0
        },
        "others": {
          "download": 10,
          "upload": 6
        }
      }
    },
    "3": {
      "name": "T-Mobile (RM520)",
      "portType": "ethernet",
      "virtual": false,
      "overall": {
        "download": 120,
        "upload": 9
      },
      "details": {
        "http": {
          "download": 118,
          "upload": 7
        },
        "https": {
          "download": 0,
          "upload": 0
        },
        "imap": {
          "download": 0,
          "upload": 0
        },
        "pop3": {
          "download": 0,
          "upload": 0
        },
        "smtp": {
          "download": 0,
          "upload": 0
        },
        "others": {
          "download": 1,
          "upload": 1
        }
      }
    },
    "order": [
      1,
      2,
      3
    ]
  },
  "traffic": {
    "timestamp": 1741891413,
    "unit": "MB",
    "1": {
      "name": "Peak Wifi",
      "portType": "ethernet",
      "virtual": false,
      "overall": {
        "download": 150791,
        "upload": 109331
      }
    },
    "2": {
      "name": "T-Mobile (RM550)",
      "portType": "ethernet",
      "virtual": false,
      "overall": {
        "download": 15130,
        "upload": 1754
      }
    },
    "3": {
      "name": "T-Mobile (RM520)",
      "portType": "ethernet",
      "virtual": false,
      "overall": {
        "download": 3379,
        "upload": 468
      }
    },
    "order": [
      1,
      2,
      3
    ]
  }
}
```

#### Reading Fan Speeds

URL Example: https://10.10.10.1/cgi-bin/MANGA/api.cgi?func=status.system.info&infoType=fanSpeed&_=1741816779871

Example response: 
```json
{
  "fanSpeed": [
    {
      "active": true,
      "value": 0,
      "total": 17000,
      "percentage": 0.0
    },
    {
      "active": true,
      "value": 0,
      "total": 17000,
      "percentage": 0.0
    }
  ]
}
```

#### Reading Thermal Sensors

URL Example: https://10.10.10.1/cgi-bin/MANGA/api.cgi?func=status.system.info&infoType=thermalSensor&_=1741816779871

Example response: 
```json
{
  "thermalSensor": [
    {
      "max": 110.0,
      "min": -30.0,
      "threshold": 30.0,
      "temperature": 37.0
    }
  ]
}
