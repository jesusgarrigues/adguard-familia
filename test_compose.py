"""Verify host-port interpolation with the real Compose parser, without starting containers."""
import json, os, shutil, subprocess, tempfile
from pathlib import Path

for file in ('compose.yaml','compose.build.yaml'):
    for port in (None,'8090'):
        env=dict(os.environ,DOCKERHUB_USERNAME='jesusgarrigues',BIND_ADDRESS='127.0.0.1')
        env.pop('APP_PORT',None)
        if port is not None: env['APP_PORT']=port
        with tempfile.TemporaryDirectory() as folder:
            shutil.copyfile(file,Path(folder)/file)
            shutil.copyfile('.env.example',Path(folder)/'.env')
            data=json.loads(subprocess.check_output(['docker','compose','--env-file','.env','-f',file,'config','--format','json'],env=env,text=True,cwd=folder))
        published=data['services']['companion']['ports'][0]
        assert published['target']==8080,published
        assert str(published['published'])==(port or '8080'),published
        assert published['host_ip']=='127.0.0.1',published
        if file=='compose.yaml':
            assert data['services']['companion']['image']=='jesusgarrigues/parental:latest'
            assert data['services']['preparar-datos']['image']=='jesusgarrigues/parental:latest'
        assert data['services']['companion']['volumes'][0]['source']=='companion-data'
print('Compose: default/custom host port validated in both installation variants; internal port remains 8080')
