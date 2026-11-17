from .access import RealmScopedReadOnlyViewSet
from .models import Role
from .permissions import HasRealmPermission, InRealm
from .serializers import RoleSerializer


class RoleViewSet(RealmScopedReadOnlyViewSet):
    """The company's roles. For whoever may see users, as roles are what users are given."""

    permission_classes = [InRealm, HasRealmPermission("users.view")]
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    lookup_value_regex = r"\d+"
