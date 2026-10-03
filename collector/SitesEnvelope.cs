using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace NoseCalibration;

// Pure format helper only. No network, key storage, session mutation or sharing UI.
internal static class SitesEnvelope
{
    internal const string StudyNamespace = "nose-calibration/sites/v1";
    internal const string RecipientKeyId = "d23bfc4486b4a270db2a479de1b9f2dee6907d7ae4113f3110633bc763009661";
    internal const int MaxPlain = 30 * 1024 * 1024, MaxEnvelope = 31 * 1024 * 1024, MaxHeader = 8192;
    internal static void ValidateBootstrap(int protocolVersion,string studyNamespace,string recipientKeyId,string participantId)
    {
        if(protocolVersion!=2 || studyNamespace!=StudyNamespace || recipientKeyId!=RecipientKeyId || !ValidId(participantId))
            throw new InvalidDataException("sites_identity_binding_invalid");
    }
    static bool ValidId(string value)=>value!=null && Regex.IsMatch(value,@"\A[a-f0-9]{32}\z");
    internal static byte[] Encrypt(byte[] plain,string participantId,string sessionId,string publicKeyPem)
    {
        if(plain==null || plain.Length<1 || plain.Length>MaxPlain || !ValidId(participantId) || !ValidId(sessionId))
            throw new InvalidDataException("sites_envelope_input_invalid");
        using var rsa=RSA.Create();rsa.ImportFromPem(publicKeyPem);
        if(rsa.KeySize!=3072 || Convert.ToHexString(SHA256.HashData(rsa.ExportSubjectPublicKeyInfo())).ToLowerInvariant()!=RecipientKeyId)
            throw new InvalidDataException("recipient_key_setup_invalid");
        string aad=$"{StudyNamespace}:2:{participantId}:{sessionId}:{RecipientKeyId}";
        byte[] key=RandomNumberGenerator.GetBytes(32),nonce=RandomNumberGenerator.GetBytes(12),tag=new byte[16],ciphertext=new byte[plain.Length];
        try
        {
            using var aes=new AesGcm(key,16);
            aes.Encrypt(nonce,plain,ciphertext,tag,Encoding.ASCII.GetBytes(aad));
            byte[] header=JsonSerializer.SerializeToUtf8Bytes(new {version=2,studyNamespace=StudyNamespace,participantId,sessionId,recipientKeyId=RecipientKeyId,aad,
                wrappedKey=Convert.ToBase64String(rsa.Encrypt(key,RSAEncryptionPadding.OaepSHA256)),nonce=Convert.ToBase64String(nonce),tag=Convert.ToBase64String(tag)});
            if(header.Length>MaxHeader)throw new InvalidDataException("sites_header_too_large");
            byte[] result=new byte[6+header.Length+1+ciphertext.Length];
            Encoding.ASCII.GetBytes("NOSE2\n").CopyTo(result,0);header.CopyTo(result,6);result[6+header.Length]=(byte)'\n';ciphertext.CopyTo(result,7+header.Length);
            if(result.Length>MaxEnvelope)throw new InvalidDataException("sites_envelope_too_large");
            return result;
        }
        finally { CryptographicOperations.ZeroMemory(key); }
    }
}
