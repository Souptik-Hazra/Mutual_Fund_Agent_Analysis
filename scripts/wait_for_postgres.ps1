$deadline = (Get-Date).AddSeconds(120)

while ((Get-Date) -lt $deadline) {
    $client = $null
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.Connect("127.0.0.1", 5432)
        $client.Close()
        Write-Host "PostgreSQL is accepting connections."
        exit 0
    }
    catch {
        if ($client) { $client.Close() }
        Start-Sleep -Seconds 2
    }
}

Write-Error "PostgreSQL did not become available within 120 seconds."
exit 1
