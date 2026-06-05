"""路线规划模块"""
from typing import List, Dict, Any, Tuple, Optional
import math


class RoutePlanner:
    """路线规划器 - 优化出行路线"""

    def __init__(self):
        self.max_walking_minutes = 30  # 最大步行时间
        self.preferred_transport = "地铁"  # 优先交通方式

    def plan_route(
        self,
        start_location: str,
        waypoints: List[Dict[str, Any]],
        end_location: Optional[str] = None,
        transport_mode: str = "地铁"
    ) -> Dict[str, Any]:
        """
        规划路线

        Args:
            start_location: 起点
            waypoints: 经过的点 [{name, location, duration, ...}]
            end_location: 终点（可选）
            transport_mode: 交通方式

        Returns:
            路线规划结果
        """
        if not waypoints:
            return {"route": [], "total_duration": 0, "total_distance": 0}

        # 简化：按顺序访问所有点
        route = []
        current_time = "09:00"

        for i, wp in enumerate(waypoints):
            # 到达时间
            arrival = current_time

            # 游玩时间
            duration = wp.get("suggested_duration", "1-2小时")
            duration_hours = self._parse_duration(duration)

            # 离开时间
            leave = self._add_hours(arrival, duration_hours)

            route.append({
                "order": i + 1,
                "name": wp.get("name", ""),
                "arrival": arrival,
                "duration": duration,
                "leave": leave,
                "location": wp.get("location", ""),
                "tips": wp.get("tips", [])
            })

            # 更新当前时间
            current_time = self._add_hours(leave, 0.5)  # 30分钟交通时间

        return {
            "route": route,
            "total_duration": len(waypoints) * 2,  # 简化估算
            "total_distance": len(waypoints) * 2,  # 简化估算
            "transport_mode": transport_mode
        }

    def optimize_visit_order(
        self,
        locations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        优化访问顺序 - 简单的贪心算法

        对于小规模问题使用贪心，对于大规模问题可以改用TSP算法
        """
        if len(locations) <= 2:
            return locations

        # 简化：按地理顺序或随机顺序
        # 实际应该计算地理位置相邻的点
        return locations

    def estimate_travel_time(
        self,
        from_loc: str,
        to_loc: str,
        mode: str = "地铁"
    ) -> Dict[str, Any]:
        """
        估算交通时间和费用

        简化实现，实际应该调用地图API
        """
        time_map = {
            "地铁": {"time": 15, "cost": 7},
            "公交": {"time": 25, "cost": 3},
            "打车": {"time": 10, "cost": 30},
            "步行": {"time": 30, "cost": 0},
        }

        defaults = time_map.get(mode, {"time": 20, "cost": 10})

        return {
            "duration_minutes": defaults["time"],
            "cost": defaults["cost"],
            "distance_km": defaults["time"] * 0.5,  # 简化估算
            "mode": mode
        }

    def group_by_area(
        self,
        locations: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        按区域分组

        将景点按区域分组，便于安排在同一天的同一区域
        """
        areas = {}

        for loc in locations:
            area = loc.get("area", loc.get("city", "其他"))
            if area not in areas:
                areas[area] = []
            areas[area].append(loc)

        return areas

    def plan_by_area(
        self,
        locations: List[Dict[str, Any]],
        locations_per_day: int = 4
    ) -> List[List[Dict[str, Any]]]:
        """
        按区域规划 - 将相邻区域的景点安排在同一天
        """
        # 按区域分组
        areas = self.group_by_area(locations)

        # 分配到每天
        daily_groups = []
        current_day = []

        for area, locs in areas.items():
            for loc in locs:
                if len(current_day) >= locations_per_day:
                    daily_groups.append(current_day)
                    current_day = []
                current_day.append(loc)

        if current_day:
            daily_groups.append(current_day)

        return daily_groups

    def find_nearest(
        self,
        from_location: Dict[str, Any],
        candidates: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """找到最近的点"""
        if not candidates:
            return None

        # 简化：使用坐标计算距离
        from_lat = from_location.get("latitude", 0)
        from_lng = from_location.get("longitude", 0)

        nearest = None
        min_distance = float("inf")

        for candidate in candidates:
            to_lat = candidate.get("latitude", 0)
            to_lng = candidate.get("longitude", 0)

            distance = self._haversine(from_lat, from_lng, to_lat, to_lng)

            if distance < min_distance:
                min_distance = distance
                nearest = candidate

        return nearest

    def _haversine(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> float:
        """计算两点之间的距离（km）"""
        R = 6371  # 地球半径

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_lat / 2) ** 2 +
            math.cos(lat1_rad) * math.cos(lat2_rad) *
            math.sin(delta_lon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def _parse_duration(self, duration_str: str) -> float:
        """解析时长字符串"""
        if not duration_str:
            return 1.0

        # 尝试解析 "1-2小时" 或 "2小时"
        import re

        match = re.search(r"(\d+)(?:-(\d+))?小时", duration_str)
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else start
            return (start + end) / 2

        # 尝试解析分钟
        match = re.search(r"(\d+)分钟", duration_str)
        if match:
            return int(match.group(1)) / 60

        return 1.0  # 默认1小时

    def _add_hours(self, time_str: str, hours: float) -> str:
        """给时间加上小时数"""
        import re

        match = re.match(r"(\d+):(\d+)", time_str)
        if not match:
            return time_str

        h, m = int(match.group(1)), int(match.group(2))
        total_minutes = h * 60 + m + int(hours * 60)

        new_h = (total_minutes // 60) % 24
        new_m = total_minutes % 60

        return f"{new_h:02d}:{new_m:02d}"
