# -*- coding: utf-8 -*-
# This file is part of Shuup.
#
# Copyright (c) 2012-2018, Shuup Inc. All rights reserved.
#
# This source code is licensed under the OSL-3.0 license found in the
# LICENSE file in the root directory of this source tree.
import json

import pytest
import six
from bs4 import BeautifulSoup
from django.utils.encoding import force_text
from django.utils.translation import activate

from shuup.admin.modules.products.views import ProductEditView
from shuup.core.models import Product
from shuup.core.models import Shop
from shuup.core.models import ShopProduct
from shuup.core.models import ShopProductVisibility
from shuup.testing.factories import (
    CategoryFactory, create_random_order, create_random_person,
    get_default_category, get_default_product, get_default_shop,
    create_product)
from shuup.testing.soup_utils import extract_form_fields
from shuup.testing.utils import apply_request_middleware
from shuup.utils.importing import load


@pytest.mark.parametrize("class_spec", [
    "shuup.admin.modules.categories.views.list:CategoryListView",
    "shuup.admin.modules.contacts.views:ContactListView",
    "shuup.admin.modules.orders.views:OrderListView",
    "shuup.admin.modules.products.views:ProductListView",
])
@pytest.mark.django_db
def test_list_view(rf, class_spec, admin_user):
    shop = get_default_shop()
    view = load(class_spec).as_view()
    request = apply_request_middleware(rf.get("/", {
        "jq": json.dumps({"perPage": 100, "page": 1})
    }), user=admin_user)
    response = view(request)
    assert 200 <= response.status_code < 300


def random_order():
    # These are prerequisites for random orders
    contact = create_random_person()
    product = get_default_product()
    return create_random_order(contact, [product])


@pytest.mark.parametrize("model_and_class", [
    (get_default_category, "shuup.admin.modules.categories.views:CategoryEditView"),
    (create_random_person, "shuup.admin.modules.contacts.views:ContactDetailView"),
    (random_order, "shuup.admin.modules.orders.views:OrderDetailView"),
    (get_default_product, "shuup.admin.modules.products.views:ProductEditView"),
])
@pytest.mark.django_db
def test_detail_view(rf, admin_user, model_and_class):
    get_default_shop()  # obvious prerequisite
    model_func, class_spec = model_and_class
    model = model_func()
    view = load(class_spec).as_view()
    request = apply_request_middleware(rf.get("/"), user=admin_user)

    if model_func == get_default_product:
        pk = model.shop_products.first().pk
    else:
        pk = model.pk

    response = view(request, pk=pk)
    if hasattr(response, "render"):
        response.render()
    assert 200 <= response.status_code < 300


@pytest.mark.django_db
def test_edit_view_adding_messages_to_form_group(rf, admin_user):
    shop = get_default_shop()  # obvious prerequisite
    product = get_default_product()
    shop_product = product.get_shop_instance(shop)
    view = ProductEditView.as_view()
    request = apply_request_middleware(rf.get("/"), user=admin_user)
    response = view(request, pk=shop_product.pk)
    response.render()
    assert 200 <= response.status_code < 300

    assert ProductEditView.add_form_errors_as_messages

    content = force_text(response.content)
    post = extract_form_fields(BeautifulSoup(content))
    post_data = {
        # Error in the base form part
        "base-name__en": "",
    }
    post.update(post_data)
    request = apply_request_middleware(rf.post("/", post), user=admin_user)
    response = view(request, pk=shop_product.pk)

    errors = response.context_data["form"].errors

    assert "base" in errors
    assert "name__en" in errors["base"]


@pytest.mark.django_db
def test_product_edit_view(rf, admin_user, settings):
    shop = get_default_shop()  # obvious prerequisite
    shop.staff_members.add(admin_user)
    product = get_default_product()
    shop_product = product.get_shop_instance(shop)
    cat = CategoryFactory()

    assert not shop_product.categories.exists()
    assert not shop_product.primary_category

    view = ProductEditView.as_view()
    request = apply_request_middleware(rf.get("/"), user=admin_user)
    response = view(request, pk=shop_product.pk)
    response.render()

    content = force_text(response.content)
    post = extract_form_fields(BeautifulSoup(content))

    # Needed for Django 1.8 tests to pass
    post.update({
        'shop1-default_price_value': '42',
        'images-TOTAL_FORMS': '0',
        'media-TOTAL_FORMS': '0',
        'base-name__fi': 'test',
        'base-name__it': 'test',
        'base-name__ja': 'test',
        'base-name__pt-br': 'test',
        'base-name__zh-hans': 'test',
    })

    post_data = {
        'shop1-primary_category': [],
        'shop1-categories': []
    }
    post.update(post_data)
    request = apply_request_middleware(rf.post("/", post), user=admin_user)
    response = view(request, pk=shop_product.pk)

    shop_product.refresh_from_db()
    assert not shop_product.categories.exists()
    assert not shop_product.primary_category

    post_data = {
        'shop1-default_price_value': 12,
        'shop1-primary_category': [cat.pk],
        'shop1-categories': []
    }
    post.update(post_data)
    usable_post = {}
    for k, v in six.iteritems(post):
        if not k:
            continue
        if not post[k]:
            continue
        usable_post[k] = v

    request = apply_request_middleware(rf.post("/", usable_post), user=admin_user)
    response = view(request, pk=shop_product.pk)

    shop_product = ShopProduct.objects.first()
    assert shop_product.primary_category

    if settings.SHUUP_AUTO_SHOP_PRODUCT_CATEGORIES:
        assert shop_product.categories.count() == 1
        assert shop_product.categories.first() == cat
    else:
        assert not shop_product.categories.count()

    assert shop_product.primary_category == cat

    post_data = {
        'shop1-primary_category': [],
        'shop1-categories': []
    }
    usable_post.update(post_data)

    request = apply_request_middleware(rf.post("/", usable_post), user=admin_user)
    response = view(request, pk=shop_product.pk)

    # empty again
    shop_product = ShopProduct.objects.first()
    assert not shop_product.categories.exists()
    assert not shop_product.primary_category

    post_data = {
        'shop1-primary_category': [],
        'shop1-categories': [cat.pk]
    }
    usable_post.update(post_data)

    request = apply_request_middleware(rf.post("/", usable_post), user=admin_user)
    response = view(request, pk=shop_product.pk)

    shop_product = ShopProduct.objects.first()
    assert shop_product.categories.count() == 1
    assert shop_product.categories.first() == cat
    if settings.SHUUP_AUTO_SHOP_PRODUCT_CATEGORIES:
        assert shop_product.primary_category == cat
    else:
        assert not shop_product.primary_category

    cat2 = CategoryFactory()

    post_data = {
        'shop1-primary_category': [],
        'shop1-categories': [cat.pk, cat2.pk]
    }
    usable_post.update(post_data)

    request = apply_request_middleware(rf.post("/", usable_post), user=admin_user)
    response = view(request, pk=shop_product.pk)

    shop_product = ShopProduct.objects.first()
    assert shop_product.categories.count() == 2
    assert cat in shop_product.categories.all()
    assert cat2 in shop_product.categories.all()
    if settings.SHUUP_AUTO_SHOP_PRODUCT_CATEGORIES:
        assert shop_product.primary_category == cat
    else:
        assert not shop_product.primary_category


@pytest.mark.django_db
def test_product_edit_view_multishop(rf, admin_user, settings):
    activate("en")

    product = create_product(sku="TEST-SKU-HAHA")

    for i in range(5):
        shop = Shop.objects.create(name="test-%d" % i)
        sp = ShopProduct.objects.create(
            product=product, shop=shop, visibility=ShopProductVisibility.ALWAYS_VISIBLE
        )

    assert Product.objects.count() == 1

    view = ProductEditView.as_view()
    for shop_product in ShopProduct.objects.all():
        request = apply_request_middleware(rf.get("/"), user=admin_user)
        response = view(request, pk=shop_product.pk)
        response.render()
        content = force_text(response.content)
        assert product.sku in content
