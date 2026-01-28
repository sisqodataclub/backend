from django.core.management.base import BaseCommand
from django.db.models import Count
from core.models import Tenant


class Command(BaseCommand):
    help = 'List all tenants with detailed information'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--active-only',
            action='store_true',
            help='Show only active tenants'
        )
        parser.add_argument(
            '--inactive-only',
            action='store_true',
            help='Show only inactive tenants'
        )
        parser.add_argument(
            '--with-stats',
            action='store_true',
            help='Show tenant statistics (slower)'
        )
        parser.add_argument(
            '--format',
            type=str,
            choices=['table', 'json', 'csv'],
            default='table',
            help='Output format'
        )
    
    def handle(self, *args, **options):
        tenants = Tenant.objects.all()
        
        if options['active_only']:
            tenants = tenants.filter(is_active=True)
            status_filter = "Active"
        elif options['inactive_only']:
            tenants = tenants.filter(is_active=False)
            status_filter = "Inactive"
        else:
            status_filter = "All"
        
        if options['format'] == 'json':
            self._output_json(tenants, options['with_stats'])
        elif options['format'] == 'csv':
            self._output_csv(tenants)
        else:
            self._output_table(tenants, status_filter, options['with_stats'])
    
    def _output_table(self, tenants, status_filter, with_stats):
        """Output as formatted table"""
        from django.apps import apps
        
        self.stdout.write(
            self.style.SUCCESS(f'\n📋 {status_filter} Tenants ({tenants.count()})\n')
        )
        self.stdout.write('─' * 90)
        self.stdout.write(
            f"{'Status':^8} | {'Name':<15} | {'Domain':<25} | {'Business Name':<20} | {'Created':<10}"
        )
        self.stdout.write('─' * 90)
        
        for tenant in tenants:
            status = '🟢' if tenant.is_active else '🔴'
            created = tenant.created_at.strftime('%Y-%m-%d')
            self.stdout.write(
                f"   {status:^3}   | {tenant.name:<15} | {tenant.domain:<25} | "
                f"{tenant.business_name[:20]:<20} | {created:<10}"
            )
        
        self.stdout.write('─' * 90)
        
        # Statistics if requested
        if with_stats and tenants.exists():
            self.stdout.write('\n📊 Tenant Statistics:')
            for tenant in tenants:
                stats = []
                for model in apps.get_models():
                    if hasattr(model, 'tenant'):
                        count = model.all_objects.filter(tenant=tenant).count()
                        if count > 0:
                            stats.append(f"{model._meta.verbose_name_plural}: {count}")
                
                if stats:
                    self.stdout.write(f"\n  {tenant.name}:")
                    for stat in stats[:3]:  # Show top 3
                        self.stdout.write(f"    • {stat}")
                    if len(stats) > 3:
                        self.stdout.write(f"    • ... and {len(stats) - 3} more")
    
    def _output_json(self, tenants, with_stats):
        """Output as JSON"""
        import json
        from django.core import serializers
        
        data = []
        for tenant in tenants:
            tenant_data = {
                'id': tenant.id,
                'name': tenant.name,
                'domain': tenant.domain,
                'business_name': tenant.business_name,
                'email': tenant.email,
                'phone': tenant.phone,
                'is_active': tenant.is_active,
                'created_at': tenant.created_at.isoformat(),
                'updated_at': tenant.updated_at.isoformat(),
            }
            
            if with_stats:
                tenant_data['stats'] = self._get_tenant_stats(tenant)
            
            data.append(tenant_data)
        
        self.stdout.write(json.dumps(data, indent=2))
    
    def _output_csv(self, tenants):
        """Output as CSV"""
        import csv
        import sys
        
        writer = csv.writer(sys.stdout)
        writer.writerow(['ID', 'Name', 'Domain', 'Business Name', 'Email', 'Phone', 'Active', 'Created'])
        
        for tenant in tenants:
            writer.writerow([
                tenant.id,
                tenant.name,
                tenant.domain,
                tenant.business_name,
                tenant.email,
                tenant.phone,
                'Yes' if tenant.is_active else 'No',
                tenant.created_at.strftime('%Y-%m-%d')
            ])
    
    def _get_tenant_stats(self, tenant):
        """Get statistics for a tenant"""
        from django.apps import apps
        
        stats = {}
        for model in apps.get_models():
            if hasattr(model, 'tenant'):
                count = model.all_objects.filter(tenant=tenant).count()
                if count > 0:
                    stats[model._meta.model_name] = count
        
        return stats