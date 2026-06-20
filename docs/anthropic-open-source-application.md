# Claude for Open Source application draft

## Project

We are building an open-source VPN platform for people living under internet blocking, censorship, throttling, and restrictions on access to independent information. This is especially important for users in Russia in 2026, but the problem is global: many countries restrict information and freedom of speech. Our goal is to help people purchase and use reliable, fault-tolerant VPN access, even when individual nodes, routes, domains, or infrastructure providers are blocked or degraded.

## Repositories

- `lannister-dev/vpn-control-api` - FastAPI control plane: users, plans, subscriptions, VPN keys, routing, placements, probes, billing, support, admin UI, metrics, and reconcilers.
- `lannister-dev/go-node-agent` - Go node agent running on VPN edge nodes: bootstrap, NATS control channel, heartbeats, routing updates, sing-box/Xray integration, graceful backend flips, metrics.
- `lannister-dev/infra` - infrastructure repository: Terraform, Ansible, K3s, Helm, WireGuard/Xray deployment, operational scripts, and runbooks.

## Short Application Text

We maintain an open-source VPN platform for censorship-resistant internet access. It is built for people in Russia and other countries where access to independent information and freedom of speech are restricted. The platform helps users purchase and use reliable VPN access, while giving operators the tooling needed to keep the service working when nodes, routes, domains, or infrastructure providers are blocked or degraded.

The project is split across three repositories: `vpn-control-api` for the FastAPI control plane, subscriptions, routing, billing, support, admin UI, and background reconcilers; `go-node-agent` for the Go agent that runs on VPN nodes and applies routing/placement changes safely; and `infra` for Terraform, Ansible, K3s, Helm, WireGuard/Xray deployment, and operational runbooks.

We do not have 5,000 GitHub stars, but this is infrastructure people can depend on when access to information is restricted. Our long-term plan is to grow this into a SaaS/control-plane platform for other VPN providers, so independent teams can run resilient VPN services without rebuilding billing, routing, node management, monitoring, and support systems from scratch.

Claude is already part of our daily engineering workflow for architecture, code review, debugging, tests, documentation, and operations. Claude Max would materially help us improve reliability, move faster, and make the platform easier for other VPN operators to adopt. We would be deeply grateful for the opportunity.

## Fill Before Submission

- Public URLs:
- License:
- Stars:
- Maintainers:
- Recent activity:
- Current users/operators:

