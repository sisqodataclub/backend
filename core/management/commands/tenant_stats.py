from django.core.management.base import BaseCommand
from django.db.models import Q, Count
from django.utils import timezone
from core.models import Tenant


class Command(BaseCommand):
    help = 'Show detailed tenant statistics and system health'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'tenant',
            nargs='?',
            type=str,
            help='Specific tenant name or domain (optional)'
        )
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed model-by-model statistics'
        )
        parser.add_argument(
            '--health',
            action='store_true',
            help='Show system health check'
        )
    
    def handle(self, *args, **options):
        if options['health']:
            self._show_system_health()
            return
        
        if options['tenant']:
            # Show stats for specific tenant
            tenant = Tenant.objects.filter(
                Q(name=options['tenant']) | Q(domain=options['tenant'])
            ).first()
            
            if not tenant:
                self.stdout.write(
                    self.style.ERROR(f'❌ Tenant not found: {options["tenant"]}')
                )
                return
            
            self._show_tenant_stats(tenant, options['detailed'])
        else:
            # Show system-wide statistics
            self._show_system_stats(options['detailed'])
    
    def _show_system_health(self):
        """Show system health information"""
        from django.db import connection
        from django.core.cache import cache
        
        self.stdout.write(self.style.SUCCESS('\n🏥 SYSTEM HEALTH CHECK\n'))
        
        # Database connection
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            self.stdout.write(f'✅ Database: Connected')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Database: Error - {e}'))
        
        # Cache
        try:
            cache.set('health_check', 'ok', 1)
            if cache.get('health_check') == 'ok':
                self.stdout.write(f'✅ Cache: Working')
            else:
                self.stdout.write(self.style.WARNING(f'⚠️ Cache: Issues detected'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Cache: Error - {e}'))
        
        # Tenant statistics
        total_tenants = Tenant.objects.count()
        active_tenants = Tenant.objects.filter(is_active=True).count()
        inactive_tenants = total_tenants - active_tenants
        
        self.stdout.write(f'\n👥 Tenants: {total_tenants} total')
        self.stdout.write(f'   • Active: {active_tenants}')
        self.stdout.write(f'   • Inactive: {inactive_tenants}')
        
        # Recent activity
        recent = Tenant.objects.filter(
            created_at__gte=timezone.now() - timezone.timedelta(days=7)
        ).count()
        self.stdout.write(f'   • Created last 7 days: {recent}')
        
        self.stdout.write('\n✅ System is healthy')
    
    def _show_system_stats(self, detailed):
        """Show statistics for all tenants"""
        from django.apps import apps
        
        tenants = Tenant.objects.all()
        
        self.stdout.write(self.style.SUCCESS('\n📊 SYSTEM STATISTICS\n'))
        
        # Summary
        self.stdout.write(f'Total Tenants: {tenants.count()}')
        self.stdout.write(f'Active Tenants: {tenants.filter(is_active=True).count()}')
        self.stdout.write(f'Inactive Tenants: {tenants.filter(is_active=False).count()}')
        
        if detailed:
            self.stdout.write('\n' + '─' * 60)
            
            # Show data distribution
            self.stdout.write('\n📦 DATA DISTRIBUTION:\n')
            
            # Get all tenant-aware models
            tenant_models = []
            for model in apps.get_models():
                if hasattr(model, 'tenant'):
                    tenant_models.append(model)
            
            for model in tenant_models:
                total = model.all_objects.count()
                if total > 0:
                    # Get top 5 tenants by record count
                    top_tenants = model.all_objects.values(
                        'tenant__name'
                    ).annotate(
                        count=Count('id')
                    ).order_by('-count')[:5]
                    
                    if top_tenants:
                        self.stdout.write(f'\n{model._meta.verbose_name_plural}: {total:,} total')
                        for item in top_tenants:
                            self.stdout.write(f'  • {item["tenant__name"]}: {item["count"]:,}')
        
        self.stdout.write('\n' + '═' * 60)
        self.stdout.write('💡 Tip: Use --detailed flag for more information')
    
    def _show_tenant_stats(self, tenant, detailed):
        """Show detailed statistics for a specific tenant"""
        from django.apps import apps
        
        self.stdout.write(self.style.SUCCESS(f'\n📊 STATISTICS FOR: {tenant.name}\n'))
        
        # Basic info
        self.stdout.write(f'Domain: {tenant.domain}')
        self.stdout.write(f'Business Name: {tenant.business_name or "N/A"}')
        self.stdout.write(f'Status: {"🟢 Active" if tenant.is_active else "🔴 Inactive"}')
        self.stdout.write(f'Created: {tenant.created_at.strftime("%Y-%m-%d")}')
        self.stdout.write(f'Last Updated: {tenant.updated_at.strftime("%Y-%m-%d")}')
        
        # Data statistics
        self.stdout.write('\n📦 DATA RECORDS:')
        
        total_records = 0
        model_counts = []
        
        for model in apps.get_models():
            if hasattr(model, 'tenant'):
                count = model.all_objects.filter(tenant=tenant).count()
                if count > 0:
                    model_counts.append((model._meta.verbose_name_plural, count))
                    total_records += count
        
        if not model_counts:
            self.stdout.write('  No data records found')
            return
        
        # Sort by count descending
        model_counts.sort(key=lambda x: x[1], reverse=True)
        
        for model_name, count in model_counts:
            percentage = (count / total_records * 100) if total_records > 0 else 0
            bar_length = int(percentage / 5)  # Scale to 20 chars
            bar = '█' * bar_length + '░' * (20 - bar_length)
            
            self.stdout.write(f'  {model_name:<20} {count:>6,}  {bar} {percentage:5.1f}%')
        
        self.stdout.write(f'\n  {"Total:":<20} {total_records:>6,}')
        
        # Show detailed breakdown if requested
        if detailed:
            self.stdout.write('\n' + '─' * 60)
            self.stdout.write('\n🔍 DETAILED BREAKDOWN:\n')
            
            for model in apps.get_models():
                if hasattr(model, 'tenant'):
                    count = model.all_objects.filter(tenant=tenant).count()
                    if count > 0:
                        # Get field distributions for key fields
                        self.stdout.write(f'\n{model._meta.verbose_name_plural}:')
                        
                        # Try to get status distribution
                        if hasattr(model, 'status'):
                            status_dist = model.all_objects.filter(
                                tenant=tenant
                            ).values('status').annotate(
                                count=Count('id')
                            ).order_by('-count')
                            
                            for item in status_dist[:5]:
                                self.stdout.write(f'  • {item["status"]}: {item["count"]:,}')
                        
                        # Try to get date distribution
                        if hasattr(model, 'created_at'):
                            recent = model.all_objects.filter(
                                tenant=tenant,
                                created_at__gte=timezone.now() - timezone.timedelta(days=30)
                            ).count()
                            self.stdout.write(f'  • Last 30 days: {recent:,}')