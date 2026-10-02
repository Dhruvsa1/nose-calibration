"""Offline C# upload recovery tests: fake HTTP only, generated key, synthetic config."""
from pathlib import Path
import subprocess
import tempfile
from xml.sax.saxutils import escape

def main():
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix='nose-upload-harness-') as directory:
        directory = Path(directory)
        (directory/'Harness.cs').write_text((root/'tools/UploadHarness.cs.txt').read_text(encoding='utf-8'), encoding='utf-8')
        source = escape(str(root/'collector/GitHubSubmission.cs'))
        auth = escape(str(root/'collector/GitHubDeviceAuth.cs'))
        (directory/'Harness.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup><ItemGroup><Compile Include="'+source+'" /><Compile Include="'+auth+'" /></ItemGroup></Project>')
        subprocess.run(['dotnet','run','--project',str(directory/'Harness.csproj')], check=True, timeout=120)

if __name__ == '__main__':
    main()
