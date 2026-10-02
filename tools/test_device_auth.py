"""Compile the real device auth module with synthetic HTTP, clock and browser only."""
from pathlib import Path
import subprocess
import tempfile
from xml.sax.saxutils import escape

def main():
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix='nose-device-auth-harness-') as directory:
        directory = Path(directory)
        (directory/'Harness.cs').write_text((root/'tools/DeviceAuthHarness.cs.txt').read_text(encoding='utf-8-sig'), encoding='utf-8')
        source = escape(str(root/'collector/GitHubDeviceAuth.cs'))
        (directory/'Harness.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup><ItemGroup><Compile Include="'+source+'" /></ItemGroup></Project>')
        subprocess.run(['dotnet','run','--project',str(directory/'Harness.csproj')], check=True, timeout=120)

if __name__ == '__main__':
    main()
