# Ref: CDO08-REL-14 - ElastiCache Valkey managed baseline for cart.
resource "aws_security_group" "elasticache_valkey" {
  name        = "techx-tf4-valkey-elasticache"
  description = "Private ElastiCache Valkey access for TechX cart migration target"
  vpc_id      = module.vpc.vpc_id

  tags = merge(var.tags, {
    Name = "techx-tf4-valkey-elasticache"
  })
}

resource "aws_vpc_security_group_ingress_rule" "elasticache_valkey_from_eks_nodes" {
  security_group_id            = aws_security_group.elasticache_valkey.id
  referenced_security_group_id = module.eks.node_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
  description                  = "Allow EKS workloads to connect to managed Valkey"
}

resource "aws_vpc_security_group_egress_rule" "elasticache_valkey_to_vpc_redis" {
  security_group_id = aws_security_group.elasticache_valkey.id
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "tcp"
  from_port         = 6379
  to_port           = 6379
  description       = "Allow online migration traffic to private Valkey source bridge"
}

resource "aws_elasticache_subnet_group" "valkey_cart" {
  name        = "techx-tf4-valkey-private"
  description = "Private subnet group for TechX cart ElastiCache Valkey"
  subnet_ids  = module.vpc.private_subnets

  tags = merge(var.tags, {
    Name = "techx-tf4-valkey-private"
  })
}

resource "aws_elasticache_parameter_group" "valkey_cart" {
  name        = "techx-tf4-valkey9-cart"
  family      = "valkey9"
  description = "Valkey 9 parameter baseline for cart migration target"

  parameter {
    name  = "maxmemory-policy"
    value = "volatile-lru"
  }

  tags = merge(var.tags, {
    Name = "techx-tf4-valkey9-cart"
  })
}

resource "aws_elasticache_replication_group" "valkey_cart" {
  replication_group_id = "techx-tf4-valkey-cart"
  description          = "Managed Valkey baseline for TechX cart migration"

  engine         = "valkey"
  engine_version = "9.0"
  node_type      = "cache.t4g.micro"
  port           = 6379

  num_cache_clusters         = 2
  automatic_failover_enabled = true
  multi_az_enabled           = true

  subnet_group_name    = aws_elasticache_subnet_group.valkey_cart.name
  security_group_ids   = [aws_security_group.elasticache_valkey.id]
  parameter_group_name = aws_elasticache_parameter_group.valkey_cart.name

  at_rest_encryption_enabled = true

  # REL-16 post-cutover hardening: Online Migration is complete, so the managed
  # target can now accept TLS clients. Keep "preferred" until Cart proves TLS
  # traffic is stable, then promote var.valkey_transit_encryption_mode to
  # "required" in a separate reviewed change.
  transit_encryption_enabled = true
  transit_encryption_mode    = var.valkey_transit_encryption_mode
  auth_token                 = var.valkey_auth_token
  auth_token_update_strategy = var.valkey_auth_token == null ? null : "SET"

  snapshot_retention_limit = 7
  snapshot_window          = "18:00-19:00"
  maintenance_window       = "sun:19:00-sun:20:00"

  auto_minor_version_upgrade = false
  # AWS requires transit encryption toggles to apply immediately.
  apply_immediately         = true
  final_snapshot_identifier = "techx-tf4-valkey-cart-final"

  tags = merge(var.tags, {
    Name = "techx-tf4-valkey-cart"
  })
}
