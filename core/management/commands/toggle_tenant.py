from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from core.models import Tenant


class Command(BaseCommand):
    help = 'Activate or deactivate a tenant'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'identifier',
            type=str,
            help='Tenant name or domain'
        )
        parser.add_argument(
            '--activate',
            action='store_true',
            help='Activate the tenant'
        )
        parser.add_argument(
            '--deactivate',
            action='store_true',
            help='Deactivate the tenant'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force operation without confirmation'
        )
    
    def handle(self, *args, **options):
        identifier = options['identifier']
        
        # Validate arguments
        if options['activate'] and options['deactivate']:
            raise CommandError('Cannot use both --activate and --deactivate')
        
        if not options['activate'] and not options['deactivate']:
            raise CommandError('Must specify either --activate or --deactivate')
        
        # Find tenant
        tenant = Tenant.objects.filter(
            Q(name=identifier) | Q(domain=identifier)
        ).first()
        
        if not tenant:
            raise CommandError(f'Tenant not found: {identifier}')
        
        # Determine action
        action = 'activate' if options['activate'] else 'deactivate'
        
        # Check if already in desired state
        if (action == 'activate' and tenant.is_active) or \
           (action == 'deactivate' and not tenant.is_active):
            
            status = "active" if tenant.is_active else "inactive"
            self.stdout.write(
                self.style.WARNING(
                    f'⚠️  Tenant "{tenant.name}" is already {status}'
                )
            )
            return
        
        # Show preview
        self.stdout.write('\n' + '═' * 50)
        self.stdout.write(f'Tenant: {tenant.name} ({tenant.domain})')
        self.stdout.write(f'Current Status: {"🟢 Active" if tenant.is_active else "🔴 Inactive"}')
        self.stdout.write(f'Action: {action.upper()}')
        self.stdout.write('═' * 50 + '\n')
        
        # Get confirmation
        if not options['force']:
            confirm = input(f'Are you sure you want to {action} this tenant? [y/N]: ')
            if confirm.lower() not in ['y', 'yes']:
                self.stdout.write(self.style.WARNING('❌ Operation cancelled'))
                return
        
        # Perform action
        if action == 'activate':
            tenant.is_active = True
            message = f'✅ Activated tenant: {tenant.name}'
            style = self.style.SUCCESS
            
            # Clear cache to reflect new status
            from django.core.cache import cache
            cache.delete(f'tenant:name:{tenant.name}')
            cache.delete(f'tenant:domain:{tenant.domain}')
            
        else:  # deactivate
            # Check for existing data
            data_count = self._count_tenant_data(tenant)
            if data_count > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f'⚠️  This tenant has {data_count} data records'
                    )
                )
                
                if not options['force']:
                    confirm = input(f'Deactivate anyway? Data will be preserved. [y/N]: ')
                    if confirm.lower() not in ['y', 'yes']:
                        self.stdout.write(self.style.WARNING('❌ Operation cancelled'))
                        return
            
            tenant.is_active = False
            message = f'✅ Deactivated tenant: {tenant.name}'
            style = self.style.SUCCESS
        
        # Save changes
        tenant.save()
        self.stdout.write(style(message))
        
        # Show new status
        self.stdout.write(f'   New Status: {"🟢 Active" if tenant.is_active else "🔴 Inactive"}')
        self.stdout.write(f'   Affected Users: {self._count_users(tenant)} active users')
    
    def _count_tenant_data(self, tenant):
        """Count data records for this tenant"""
        from django.apps import apps
        
        total = 0
        for model in apps.get_models():
            if hasattr(model, 'tenant'):
                total += model.all_objects.filter(tenant=tenant).count()
        
        return total
    
    def _count_users(self, tenant):
        """Count users associated with this tenant"""
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            if hasattr(User, 'tenant'):
                return User.objects.filter(tenant=tenant, is_active=True).count()
            return 0
        except:
            return 0