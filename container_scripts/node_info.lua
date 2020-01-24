-- Script to return public node config metadata via the config file contents.

local cjson = require("cjson")

local config_file = assert(io.open(ngx.var.chord_instance_config))
local config_params = cjson.decode(config_file:read("*all"))
config_file:close()

local response = {
  CHORD_URL=config_params["CHORD_URL"]
}

ngx.status = 200
ngx.header["Content-Type"] = "application/json"
ngx.say(cjson.encode(response))
