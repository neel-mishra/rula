# ── RDS PostgreSQL (Multi-AZ in prod, single-AZ in staging/dev) ──────────────

resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db-subnet"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_security_group" "rds" {
  name        = "${local.name_prefix}-rds-sg"
  description = "Allow Postgres from ECS tasks only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_kms_key" "rds" {
  description             = "KMS key for RDS encryption — ${local.name_prefix}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_db_instance" "main" {
  identifier        = "${local.name_prefix}-postgres"
  engine            = "postgres"
  engine_version    = "16.2"
  instance_class    = var.db_instance_class
  allocated_storage = 50
  storage_type      = "gp3"
  storage_encrypted = true
  kms_key_id        = aws_kms_key.rds.arn

  db_name  = "inbox_${var.environment}"
  username = "inbox_admin"
  # Password managed via Secrets Manager; set manually on first create
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  # Multi-AZ in prod for RPO <= 5 min target
  multi_az = var.environment == "prod"

  # Point-in-time recovery
  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  # Deletion protection in prod
  deletion_protection = var.environment == "prod"
  skip_final_snapshot = var.environment != "prod"

  # pgvector extension enabled via parameter group
  parameter_group_name = aws_db_parameter_group.pg16.name

  tags = {
    Name = "${local.name_prefix}-postgres"
  }
}

resource "aws_db_parameter_group" "pg16" {
  family = "postgres16"
  name   = "${local.name_prefix}-pg16-params"

  parameter {
    name  = "shared_preload_libraries"
    value = "vector"
  }
}

output "rds_endpoint" {
  value     = aws_db_instance.main.endpoint
  sensitive = true
}
