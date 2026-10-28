"""测试分页实用函数。"""

from dataclasses import dataclass
from typing import Any

import pytest

from openhands.sdk.utils.paging import page_iterator


@dataclass
class MockPage:
    """模拟对象用于测试的页面对象。"""

    items: list[Any]
    next_page_id: str | None = None


class MockSearchService:
    """模拟对象用于测试分页的搜索服务。"""

    def __init__(self, all_items: list[Any], page_size: int = 2):
        self.all_items = all_items
        self.page_size = page_size

    async def search(self, page_id: str | None = None, **kwargs) -> MockPage:
        """模拟对象返回分页结果的搜索方法。"""
        start_index = 0

        # 根据page_id查找起始索引
        if page_id:
            try:
                start_index = int(page_id)
            except (ValueError, TypeError):
                start_index = 0

        # 获取该页面的项目
        end_index = start_index + self.page_size
        page_items = self.all_items[start_index:end_index]

        # 确定next_page_id
        next_page_id = None
        if end_index < len(self.all_items):
            next_page_id = str(end_index)

        return MockPage(items=page_items, next_page_id=next_page_id)


@pytest.mark.asyncio
async def test_page_iterator_empty_results():
    """测试 page_iterator，结果为空。"""
    service = MockSearchService([])

    items = []
    async for item in page_iterator(service.search):
        items.append(item)

    assert items == []


@pytest.mark.asyncio
async def test_page_iterator_single_page():
    """测试 page_iterator，结果适合单页。"""
    service = MockSearchService(["item1", "item2"], page_size=5)

    items = []
    async for item in page_iterator(service.search):
        items.append(item)

    assert items == ["item1", "item2"]


@pytest.mark.asyncio
async def test_page_iterator_multiple_pages():
    """测试 page_iterator，结果跨多个页面。"""
    service = MockSearchService(
        ["item1", "item2", "item3", "item4", "item5"], page_size=2
    )

    items = []
    async for item in page_iterator(service.search):
        items.append(item)

    assert items == ["item1", "item2", "item3", "item4", "item5"]


@pytest.mark.asyncio
async def test_page_iterator_with_kwargs():
    """测试 page_iterator 传递关键字参数。"""
    service = MockSearchService(["a", "b", "c", "d"], page_size=2)

    # 模拟对象接受额外 kwargs 的搜索方法
    async def search_with_filter(
        page_id: str | None = None, filter_value: str | None = None
    ) -> MockPage:
        page = await service.search(page_id=page_id)
        if filter_value:
            # 根据 filter_value 过滤项目
            filtered_items = [item for item in page.items if filter_value in item]
            return MockPage(items=filtered_items, next_page_id=page.next_page_id)
        return page

    items = []
    async for item in page_iterator(search_with_filter, filter_value="a"):
        items.append(item)

    assert items == ["a"]


@pytest.mark.asyncio
async def test_page_iterator_with_args():
    """测试 page_iterator 传递位置参数。"""
    service = MockSearchService(["x", "y", "z"], page_size=2)

    # 模拟对象接受位置参数的搜索方法
    async def search_with_args(prefix: str, page_id: str | None = None) -> MockPage:
        page = await service.search(page_id=page_id)
        # 为每个项目添加前缀
        prefixed_items = [f"{prefix}{item}" for item in page.items]
        return MockPage(items=prefixed_items, next_page_id=page.next_page_id)

    items = []
    async for item in page_iterator(search_with_args, "prefix_"):
        items.append(item)

    assert items == ["prefix_x", "prefix_y", "prefix_z"]


@pytest.mark.asyncio
async def test_page_iterator_preserves_initial_page_id():
    """测试 page_iterator 是否尊重 kwargs 中的首字母 page_id。"""
    service = MockSearchService(["a", "b", "c", "d", "e"], page_size=2)

    # 从第二页开始（索引 2）
    items = []
    async for item in page_iterator(service.search, page_id="2"):
        items.append(item)

    assert items == ["c", "d", "e"]


@pytest.mark.asyncio
async def test_page_iterator_removes_page_id_from_kwargs():
    """测试 page_iterator 是否正确处理 kwargs 中的 page_id。"""
    service = MockSearchService(["1", "2", "3"], page_size=1)

    # 如果 page_id 出现两次，模拟对象搜索将失败
    call_count = 0

    async def strict_search(page_id: str | None = None, **kwargs) -> MockPage:
        nonlocal call_count
        call_count += 1

        # 确保 kwargs 中没有多余的 page_id
        assert "page_id" not in kwargs

        return await service.search(page_id=page_id)

    items = []
    async for item in page_iterator(strict_search, page_id="1", other_param="value"):
        items.append(item)

    assert items == ["2", "3"]
    assert call_count == 2  # 应拨打 2 次电话（从 page_id="1" 开始）


@pytest.mark.asyncio
async def test_page_iterator_complex_objects():
    """使用复杂对象测试 page_iterator。"""

    @dataclass
    class ComplexItem:
        id: int
        name: str

    complex_items = [
        ComplexItem(1, "first"),
        ComplexItem(2, "second"),
        ComplexItem(3, "third"),
    ]

    service = MockSearchService(complex_items, page_size=2)

    items = []
    async for item in page_iterator(service.search):
        items.append(item)

    assert len(items) == 3
    assert items[0].id == 1
    assert items[0].name == "first"
    assert items[1].id == 2
    assert items[1].name == "second"
    assert items[2].id == 3
    assert items[2].name == "third"
