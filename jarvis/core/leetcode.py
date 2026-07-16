from __future__ import annotations

import json
import re
import webbrowser
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


LEETCODE_BASE = "https://leetcode.com/problems/"

# Spaced-repetition intervals (in days) after a problem is solved.
REVISION_INTERVALS_DAYS = [1, 3, 7, 14, 30]

# The NeetCode 150, in roadmap order. Slugs are derived from the title, which
# matches LeetCode's URL scheme (e.g. "Two Sum" -> "two-sum", "3Sum" -> "3sum").
NEETCODE_150 = [
	# Arrays & Hashing
	"Two Sum", "Valid Anagram", "Contains Duplicate", "Valid Sudoku",
	"Longest Consecutive Sequence", "Group Anagrams", "Top K Frequent Elements",
	"Product of Array Except Self", "Encode and Decode Strings",
	# Two Pointers
	"Valid Palindrome", "Two Sum II - Input Array Is Sorted", "3Sum",
	"Container With Most Water", "Trapping Rain Water",
	# Sliding Window
	"Best Time to Buy and Sell Stock", "Longest Substring Without Repeating Characters",
	"Longest Repeating Character Replacement", "Permutation in String",
	"Minimum Window Substring", "Sliding Window Maximum",
	# Stack
	"Valid Parentheses", "Min Stack", "Evaluate Reverse Polish Notation",
	"Generate Parentheses", "Daily Temperatures", "Car Fleet",
	"Largest Rectangle in Histogram",
	# Binary Search
	"Binary Search", "Search a 2D Matrix", "Koko Eating Bananas",
	"Find Minimum in Rotated Sorted Array", "Search in Rotated Sorted Array",
	"Median of Two Sorted Arrays",
	# Linked List
	"Reverse Linked List", "Merge Two Sorted Lists", "Reorder List",
	"Remove Nth Node From End of List", "Linked List Cycle",
	"Intersection of Two Linked Lists", "Linked List Cycle II",
	"Merge k Sorted Lists", "LRU Cache", "Design Linked List",
	# Trees
	"Invert Binary Tree", "Maximum Depth of Binary Tree", "Diameter of a Binary Tree",
	"Balanced Binary Tree", "Same Tree", "Subtree of Another Tree",
	"Lowest Common Ancestor of a Binary Search Tree", "Binary Tree Level Order Traversal",
	"Binary Tree Right Side View", "Count Good Nodes in Binary Tree",
	"Validate Binary Search Tree", "Kth Smallest Element in a BST",
	"Construct Binary Tree from Preorder and Inorder Traversal",
	"Binary Tree Maximum Path Sum", "Serialize and Deserialize Binary Tree",
	# Tries
	"Implement Trie (Prefix Tree)", "Design Add and Search Words Data Structure",
	"Word Search II",
	# Heap / Priority Queue
	"K Closest Points to Origin", "Last Stone Weight", "Task Scheduler",
	"Design Twitter", "Find Median from Data Stream",
	# Backtracking
	"Subsets", "Subsets II", "Permutations", "Permutations II", "Combinations",
	"Combination Sum", "Combination Sum II", "Word Search", "N-Queens", "Sudoku Solver",
	# Graphs
	"Number of Islands", "Clone Graph", "Max Area of Island", "Pacific Atlantic Water Flow",
	"Surrounded Regions", "Rotting Oranges", "Walls and Gates", "Course Schedule",
	"Course Schedule II", "Redundant Connection",
	"Number of Connected Components in an Undirected Graph", "Graph Valid Tree",
	"Word Ladder", "Network Delay Time",
	# Advanced Graphs
	"Reconstruct Itinerary", "Min Cost to Connect All Points", "Swim in Rising Water",
	"Alien Dictionary", "Cheapest Flights Within K Stops",
	# 1-D Dynamic Programming
	"Climbing Stairs", "Min Cost Climbing Stairs", "House Robber", "House Robber II",
	"Longest Palindromic Substring", "Palindromic Substrings", "Decode Ways",
	"Coin Change", "Maximum Product Subarray", "Word Break", "Longest Increasing Subsequence",
	# 2-D Dynamic Programming
	"Unique Paths", "Longest Common Subsequence",
	"Best Time to Buy and Sell Stock with Cooldown", "Best Time to Buy and Sell Stock III",
	"Best Time to Buy and Sell Stock IV", "Edit Distance", "Burst Balloons",
	"Partition Equal Subset Sum",
	# Greedy
	"Maximum Subarray", "Jump Game", "Jump Game II", "Gas Station", "Hand of Straights",
	"Merge Triplets to Form Target Triplet", "Partition Labels", "Valid Parenthesis String",
	"Minimum Number of Arrows to Burst Balloons",
	# Intervals
	"Insert Interval", "Merge Intervals", "Non-overlapping Intervals", "Meeting Rooms",
	"Meeting Rooms II", "Minimum Interval to Include Each Query",
	# Math & Geometry
	"Rotate Image", "Spiral Matrix", "Set Matrix Zeroes", "Happy Number", "Plus One",
	"Pow(x, n)", "Multiply Strings", "Detect Squares",
	# Bit Manipulation
	"Single Number", "Maximum XOR of Two Numbers in an Array", "Sum of Two Integers",
	"Reverse Bits", "Number of 1 Bits",
]


def _slugify(value: str) -> str:
	clean = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
	return clean or "problem"


def _today() -> date:
	return datetime.now().date()


class LeetCodeTracker:
	"""Tracks NeetCode 150 progress locally and schedules revisions."""

	def __init__(self, path: Path) -> None:
		self.path = Path(path)
		self.problems: list[dict[str, Any]] = []
		self.load()

	def load(self) -> None:
		if self.path.exists():
			try:
				payload = json.loads(self.path.read_text(encoding="utf-8"))
				self.problems = payload.get("problems", [])
			except (OSError, json.JSONDecodeError):
				self.problems = []
		if not self.problems:
			self.problems = [
				{
					"name": name,
					"slug": _slugify(name),
					"solved": False,
					"solved_date": None,
					"revisions": [],
					"next_revision": None,
				}
				for name in NEETCODE_150
			]
			self.save()

	def save(self) -> None:
		self.path.parent.mkdir(parents=True, exist_ok=True)
		self.path.write_text(json.dumps({"problems": self.problems}, indent=2), encoding="utf-8")

	def _find(self, query: str) -> dict[str, Any] | None:
		q = (query or "").strip().lower()
		if not q:
			return None
		for problem in self.problems:
			if q == problem["name"].lower() or q == problem["slug"]:
				return problem
		for problem in self.problems:
			if q in problem["name"].lower() or q in problem["slug"]:
				return problem
		return None

	def next_unsolved(self) -> dict[str, Any] | None:
		for problem in self.problems:
			if not problem["solved"]:
				return problem
		return None

	def mark_solved(self, query: str) -> dict[str, Any] | None:
		problem = self._find(query)
		if problem is None:
			return None
		problem["solved"] = True
		today = _today().isoformat()
		problem["solved_date"] = today
		problem["revisions"] = [
			(_today() + timedelta(days=offset)).isoformat() for offset in REVISION_INTERVALS_DAYS
		]
		problem["next_revision"] = problem["revisions"][0]
		self.save()
		return problem

	def mark_revision_done(self, query: str) -> dict[str, Any] | None:
		problem = self._find(query)
		if problem is None:
			return None
		due = problem.get("next_revision")
		if due:
			problem["revisions"] = [r for r in problem["revisions"] if r != due]
			problem["next_revision"] = problem["revisions"][0] if problem["revisions"] else None
		self.save()
		return problem

	def due_revisions(self) -> list[dict[str, Any]]:
		today = _today()
		due = []
		for problem in self.problems:
			nr = problem.get("next_revision")
			if nr and date.fromisoformat(nr) <= today:
				due.append(problem)
		return due

	def stats(self) -> dict[str, Any]:
		total = len(self.problems)
		solved = sum(1 for p in self.problems if p["solved"])
		return {"total": total, "solved": solved, "due": len(self.due_revisions())}

	def open_problem(self, problem: dict[str, Any]) -> str:
		url = f"{LEETCODE_BASE}{problem['slug']}/"
		if os_name_nt():
			try:
				import os

				os.startfile(url)
				return url
			except Exception:
				pass
		webbrowser.open(url)
		return url

	def _find_by_index(self, number: int) -> dict[str, Any] | None:
		"""Lookup a problem by its 1-based NeetCode 150 position."""
		if 1 <= number <= len(self.problems):
			return self.problems[number - 1]
		return None

	def open_problem_by_number(self, number: int) -> str | None:
		problem = self._find_by_index(number)
		if problem is None:
			return None
		return self.open_problem(problem)


def os_name_nt() -> bool:
	import os

	return os.name == "nt"
