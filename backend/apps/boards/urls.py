from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("boards/groups", views.GroupViewSet, basename="board-group")
router.register("boards/columns", views.ColumnViewSet, basename="board-column")
router.register("boards/views", views.ViewViewSet, basename="board-view")
router.register("boards/items", views.ItemViewSet, basename="board-item")
router.register("boards", views.BoardViewSet, basename="board")

urlpatterns = router.urls
