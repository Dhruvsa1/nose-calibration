"""Build actual transport against fake HTTP; only envelope key pin changed in temporary test copy."""
from pathlib import Path
import hashlib,subprocess,tempfile
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

def main():
 root=Path(__file__).resolve().parents[1]
 key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
 pin=hashlib.sha256(key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()
 with tempfile.TemporaryDirectory(prefix='nose-sites-harness-') as temp:
  p=Path(temp);(p/'empty-feed').mkdir()
  for name in ('SitesConnection.cs','SitesSubmission.cs','SitesEnvelope.cs','GitHubSubmission.cs','GitHubDeviceAuth.cs','GitHubAppAccess.cs'):
   src=(root/'collector'/name).read_text(encoding='utf-8-sig')
   if name=='SitesEnvelope.cs':src=src.replace('d23bfc4486b4a270db2a479de1b9f2dee6907d7ae4113f3110633bc763009661',pin)
   (p/name).write_text(src)
  (p/'Program.cs').write_text((root/'tools/SitesSubmissionHarness.cs.txt').read_text(encoding='utf-8-sig'))
  (p/'key.pem').write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
  (p/'test.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>')
  sdk=root/'work/dotnet-sdk-8.0.425/dotnet.exe'
  subprocess.run([str(sdk),'restore','test.csproj','--source',str(p/'empty-feed')],cwd=p,check=True,capture_output=True,timeout=60)
  subprocess.run([str(sdk),'run','--no-restore','--project','test.csproj','--',str(p/'key.pem')],cwd=p,check=True,timeout=90)
if __name__=='__main__':main()
