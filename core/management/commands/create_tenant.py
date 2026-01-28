from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
import secrets
from core.models import Tenant

class Command(BaseCommand):
    help = 'Create a new tenant with secure defaults'
    
    def add_arguments(self, parser):
        parser.add_argument('name', type=str, help='Tenant internal name (URL-safe)')
        parser.add_argument('domain', type=str, help='Tenant domain (e.g., client.example.com)')
        parser.add_argument(
            '--business-name',
            type=str,
            default='',
            help='Public-facing business name'
        )
        parser.add_argument(
            '--email',
            type=str,
            default='',
            help='Contact email for notifications'
        )
        parser.add_argument(
            '--phone',
            type=str,
            default='',
            help='Contact phone number'
        )
        parser.add_argument(
            '--inactive',
            action='store_true',
            help='Create tenant as inactive (requires activation)'
        )
        parser.add_argument(
            '--create-default-admin',
            action='store_true',
            help='Create a default admin user for this tenant'
        )
    
    def handle(self, *args, **options):
        name = options['name']
        domain = options['domain']
        
        # Validate inputs
        if not name.isidentifier():
            raise CommandError('Tenant name must be URL-safe (letters, numbers, underscores)')
        
        if ' ' in domain:
            raise CommandError('Domain cannot contain spaces')
        
        # Check if tenant already exists
        if Tenant.objects.filter(name=name).exists():
            raise CommandError(f'Tenant with name "{name}" already exists')
        
        if Tenant.objects.filter(domain=domain).exists():
            raise CommandError(f'Tenant with domain "{domain}" already exists')
        
        # Create tenant
        tenant = Tenant.objects.create(
            name=name,
            domain=domain,
            business_name=options['business_name'] or name.title(),
            email=options['email'],
            phone=options['phone'],
            is_active=not options['inactive']
        )
        
        # Output success message
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Successfully created tenant: {tenant.name}'
            )
        )
        self.stdout.write(f'   Domain: {tenant.domain}')
        self.stdout.write(f'   Business Name: {tenant.business_name}')
        self.stdout.write(f'   Status: {"🟢 Active" if tenant.is_active else "🔴 Inactive"}')
        self.stdout.write(f'   Tenant ID: {tenant.id}')
        
        if not tenant.is_active:
            self.stdout.write(
                self.style.WARNING('\n⚠️  Tenant created as INACTIVE')
            )
            self.stdout.write('   Activate with: python manage.py toggle_tenant {name} --activate')
        
        # Optional: Create default admin user
        if options['create_default_admin']:
            self._create_default_admin(tenant)
    
    def _create_default_admin(self, tenant):
        """Create a default admin user for the tenant"""
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            # Generate secure password
            password = secrets.token_urlsafe(12)
            
            # Prepare user creation arguments
            user_kwargs = {
                'username': f'admin-{tenant.name}',
                'email': tenant.email or f'admin@{tenant.domain}',
                'password': password,
                'is_staff': True,
                'is_superuser': True
            }

            # Check if User model has a tenant field and add it to kwargs
            # This prevents IntegrityError if tenant is a required field
            field_names = [f.name for f in User._meta.get_fields()]
            if 'tenant' in field_names:
                user_kwargs['tenant'] = tenant

            # Create the user
            admin_user = User.objects.create_user(**user_kwargs)
            
            self.stdout.write(
                self.style.SUCCESS(f'\n👤 Created admin user:')
            )
            self.stdout.write(f'   Username: {admin_user.username}')
            self.stdout.write(f'   Password: {password}')
            self.stdout.write('\n⚠️  SECURITY: Change this password immediately!')
            
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'\n⚠️  Could not create admin user: {e}')
            )