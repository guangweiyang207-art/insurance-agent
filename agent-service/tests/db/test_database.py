import pytest
from sqlalchemy import select, func, desc, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db.conftest import User
from app.core.logging import get_logger, configure_logging
configure_logging(level="DEBUG")

logger = get_logger('test_crud')

@pytest.mark.asyncio
async def test_add_user(session: AsyncSession):
    """测试新增用户"""
    logger.info('**********开始*************')
    async with session.begin():
        # 新增用户
        user = User(name="虎哥", email="huge@itheima.com")
        # add方法自带回显
        session.add(user)
    logger.info('**********结束*************')

    logger.info(f'user info : {user}')

@pytest.mark.asyncio
async def test_add_users(session: AsyncSession):
    """测试批量新增"""
    users = [
        User(name="虎哥", email="huge@itheima.com"),
        User(name="柳岩", email="liuyan@itheima.com")
    ]
    logger.info('**********开始*************')
    async with session.begin():
        session.add_all(users)
    logger.info('**********结束*************')

    for user in users:
        logger.info(f"user : {user}")

@pytest.mark.asyncio
async def test_read_user_by_id(session: AsyncSession):
    """测试根据id读取用户"""
    logger.info('**********开始*************')
    # 测试查询
    result = await session.get(User, 2)
    logger.info('**********结束*************')

    logger.info(f'first type: {type(result)}')
    logger.info(f'first info: {result}')


@pytest.mark.asyncio
async def test_read_user_by_ids(session: AsyncSession, init_test_data):
    """测试根据id读取用户"""
    logger.info('**********开始*************')
    # 测试查询
    ids = [1, 2, 3]
    result = await session.execute(
        select(User).where(User.id.in_(ids))
    )
    logger.info('**********结束*************')

    # 通过scalars自动将查询的row转为表模型实体 User
    fetched = result.scalars().all()
    logger.info(f'first type: {type(fetched)}')
    logger.info(f'first info: {fetched}')


@pytest.mark.asyncio
async def test_read_user(session: AsyncSession, init_test_data):
    """测试读取一个用户"""
    logger.info('**********开始*************')
    result = await session.execute(
        select(User).where(User.email == "bob@example.com")
    )
    logger.info('**********结束*************')

    # 把查询的row转为User实体
    fetched = result.scalar_one()

    logger.info(f'first type: {type(fetched)}')
    logger.info(f'first info: {fetched}')


@pytest.mark.asyncio
async def test_read_user_field(session: AsyncSession, init_test_data):
    """测试读取用户部分字段"""

    logger.info('**********开始*************')
    result = await session.execute(
        select(User.id, User.name).where(User.email == "bob@example.com")
    )
    logger.info('**********结束*************')

    # 注意：scalar只返回select的第一列，本例中就是User.id
    # fetched = result.scalar_one()
    fetched = result.mappings().one()

    logger.info(f'first type: {type(fetched)}')
    logger.info(f'first info: {fetched}')


@pytest.mark.asyncio
async def test_read_users(session: AsyncSession, init_test_data):
    logger.info('**********开始*************')
    # 测试查询
    result = await session.execute(
        select(User).order_by(desc(User.id))
    )
    logger.info('**********结束*************')

    # 把查询的row转为User实体
    fetched = result.scalars().all()
    logger.info(f'first type: {type(fetched)}')
    logger.info(f'first info: {fetched}')

@pytest.mark.asyncio
async def test_update_user(session: AsyncSession, init_test_data):
    # 测试更新，更新时先查询，然后只需要修改user值，commit后，它会自动更新到数据库
    id = 1
    logger.info('**********开始*************')
    async with session.begin():
        # 先查询
        user = await session.get(User, id)
        logger.info(f'old user: {user}')
        # 然后修改字段，commit后，它会自动更新到数据库
        user.name = "虎哥"
        user.email = "huge@itcast.cn"
    logger.info('**********结束*************')

    # 再次查询数据库
    await session.refresh(user)
    logger.info(f'new user: {user}')

@pytest.mark.asyncio
async def test_update_user2(session: AsyncSession, init_test_data):
    """测试更新用户"""
    logger.info('**********开始*************')
    # 先查询
    async with session.begin():
        await session.execute(
            update(User).values(name="虎哥").where(User.id == 1)
        )
        logger.info('**********结束*************')

    user = await session.get(User, 1)
    logger.info(f'new user: {user}')

@pytest.mark.asyncio
async def test_delete_user(session: AsyncSession, init_test_data):
    logger.info('**********开始*************')
    async with session.begin():
        # 再删除
        await session.execute(
            delete(User).where(User.id == 2)
        )
    logger.info('**********结束*************')

    count = await session.scalar(
        select(func.count(User.id)).where(User.id == 2)
    )
    assert count == 0