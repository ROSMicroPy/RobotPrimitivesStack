
# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
import os
import json


class mipDefinition():
    def __init__(self):
        self.data = {}
        self.data["name"] = ""
        self.data["version"] = ""
        self.data["urls"] = []

    def addURL(self, url:list):
        self.data["urls"].append(list)


class mipJSON():
    def __init__(self, repoBaseURL:str):
        self.repoBaseURL = repoBaseURL;
        self.mipDef = mipDefinition()
        self.pkgName = None


    def addFiles(self, directory:str, branch:str="main"):
        """
        Creates a mip package.json from a local directory listing.
        """
        # Walk through directory to find .py and .mpy files
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith(('.py', '.mpy')):
                    # Create relative path
                    full_path = os.path.join(root, file)
                    rel_path = full_path
                    if rel_path.startswith("./"): 
                        rel_path=rel_path[2:]
                    elif rel_path.startswith("/"): 
                        rel_path=rel_path[1:]
                    
                    rel_path_store = os.path.relpath(full_path, directory)
                    if rel_path_store.startswith("./"): 
                        rel_path_store=rel_path_store[2:]
                    elif rel_path_store.startswith("/"): 
                        rel_path_store=rel_path_store[1:]

                    flist = []

                    if self.pkgName:
                        flist.append(f"{self.pkgName}/{rel_path_store}")
                    else:
                        flist.append(f"{rel_path_store}")

                    flist.append(f"{self.repoBaseURL}/{rel_path}")

                    self.mipDef.data["urls"].append(flist)

    def writeOutput(self, output_file:str="package.json"):
        # Write to package.json
        with open(output_file, 'w+') as f:
            json.dump(self.mipDef.data, f, indent=4)
        print(f"Created {output_file} for {len(self.mipDef.data['urls'])} files.")

    def setName(self, name:str):
        self.mipDef.data["name"] = name

    def setVersion(self, version:str):
        self.mipDef.data["version"] = version

    def setPkgName(self, name:str):
        self.pkgName = name
# "urls": [
#    ["dnet/__init__.py", "gitlab:robot-primitives/LighthouseMesh/-/blob/main/dnet/code/__init__.py?"],

        
#https://gitlab.com/robot-primitives/micropython_modules/mp_shell/-/blob/main/package.json?
mj = mipJSON("https://gitlab.com/robot-primitives/micropython_modules/mp_opentelemetry/-/raw/main")
mj.setVersion("1.0")
mj.setName("Micropython Open Telemetry SDK")
mj.setPkgName("otel")
mj.addFiles("./src")
mj.setPkgName("examples")
mj.addFiles("./examples")
mj.writeOutput("package.json")
