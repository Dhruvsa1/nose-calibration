namespace NoseCalibration;

// Memory-only capability with a revocable lifetime; no token/DPAPI/file persistence.
internal sealed class SitesConnection : IDisposable
{
    readonly object gate=new();
    readonly Func<string,CancellationToken,Task<string>> bootstrap;
    CancellationTokenSource? lifetime;
    string? invitation,participant;
    bool connecting,disposed;
    internal SitesConnection(Func<string,CancellationToken,Task<string>>? bootstrap=null){this.bootstrap=bootstrap??SitesSubmission.Connect;}
    internal bool Connecting {get{lock(gate)return connecting;}}
    internal string? Participant {get{lock(gate)return participant;}}
    internal sealed record Authorization(string Invitation,string ParticipantId,CancellationToken Lifetime);
    internal Authorization Acquire()
    {
        lock(gate){if(invitation==null||participant==null||lifetime==null||lifetime.IsCancellationRequested)throw new SitesSubmission.SharingError("not_connected");return new(invitation,participant,lifetime.Token);}
    }
    internal async Task Connect(string code)
    {
        CancellationTokenSource run; CancellationToken token;
        lock(gate)
        {
            ObjectDisposedException.ThrowIf(disposed,this);
            if(connecting)throw new SitesSubmission.SharingError("connection_busy");
            Disconnect();run=new CancellationTokenSource();lifetime=run;token=run.Token;connecting=true;
        }
        try
        {
            var identity=await bootstrap(code,token);
            lock(gate){token.ThrowIfCancellationRequested();if(!ReferenceEquals(lifetime,run))throw new OperationCanceledException();invitation=code;participant=identity;}
        }
        finally
        {
            lock(gate){if(ReferenceEquals(lifetime,run)){connecting=false;if(participant==null){lifetime=null;run.Dispose();}}}
        }
    }
    internal void Disconnect()
    {
        lock(gate){invitation=null;participant=null;connecting=false;var previous=lifetime;lifetime=null;if(previous!=null){previous.Cancel();previous.Dispose();}}
    }
    public void Dispose(){lock(gate){disposed=true;Disconnect();}}
}
