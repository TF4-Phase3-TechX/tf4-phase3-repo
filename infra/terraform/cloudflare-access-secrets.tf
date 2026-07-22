# CDO08-SEC-05: Cloudflare Access tunnel token placeholder.
# Terraform owns only the secret metadata. The tunnel token value is inserted
# out-of-band after apply so the token is not stored in Terraform state.
resource "aws_secretsmanager_secret" "cloudflare_tunnel_token" {
  name                    = "techx/tf4/cloudflare/tunnel-token"
  description             = "Cloudflare Tunnel token for TF4 operational portals"
  recovery_window_in_days = 30

  tags = merge(var.tags, {
    Component = "cloudflare-access"
    ManagedBy = "terraform"
    Mandate   = "01"
    Task      = "CDO08-SEC-05"
  })
}
