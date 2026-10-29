"""What Lines and Strategy share: the changes a team tab applied that are not saved yet ("mine": the foot's note,
Take back lit) and taking them back ("Take back my lines", "Take back my strategies"). docs/ui/lines.md.

A change a tab applies is a session.Change with its tab and team set (Save's My edits and the rail's dot read them).
Taking a team's changes back first drops them from the open roster's history: their records get back the bytes from
before them and My edits forgets them (no "taken back" line). When another change touched one of those records after
them (a number typed on the Roster tab, an update), dropping them would take that one back too: the values they
changed are then put back one by one instead, as one new change that My edits lists.
"""


def drop(s, changes):
    """Take `changes` back out of the roster and its history (RosterSession.drop). False: nothing was done."""
    return s.drop(changes)


class Applied:
    """One tab's applied changes: the values each changed ({key: (old, new)}, the key as the tab knows a value) and
    the take-backs done value by value (they and the changes they took back are not "mine" any more)."""

    def __init__(self, ctl, tab):
        self.ctl, self.tab = ctl, tab   # tab: the tab's label, as session.Change.tab holds it
        self.values = []                # [(change, {key: (old, new)})]
        self.backs = []                 # [(take-back change, [the changes it took back])]

    def reset(self):
        self.values, self.backs = [], []

    def note(self, ch, values):
        """A change this tab applied, with the values it changed."""
        history = self.ctl.session.history
        self.values = [(c, v) for c, v in self.values if any(c is h for h in history)] + [(ch, values)]

    def mine(self, team):
        """This team's changes from this tab that are not saved yet and not taken back, oldest first. Under the lock."""
        if self.ctl.session is None:
            return []
        pending = [ch for ch, undone in self.ctl.parts['save'].pending() if not undone]
        gone = []
        for back, took in self.backs:
            if back is None or any(back is ch for ch in pending):   # None: nothing was left to put back
                gone += [back, *took]
        return [ch for ch in pending if ch.tab == self.tab and ch.team == team and not any(ch is g for g in gone)]

    def take_back(self, team, label, restore):
        """Take this team's changes back (call under the lock). restore(setter, {key: (old, new)}) puts each old value
        back where the roster still holds the new one, through the session's setter (when they cannot be dropped).
        Returns 'dropped', the new Change (restored value by value), or None (nothing of this tab's to take back)."""
        s = self.ctl.session
        mine = self.mine(team)
        if not mine:
            return None
        if drop(s, mine):
            return 'dropped'
        values = {}
        for ch in mine:
            changed = next((v for c, v in self.values if c is ch), {})
            for key, (old, new) in changed.items():
                values[key] = (values[key][0] if key in values else old, new)
        ch, _ = s.edit(label, lambda setter: restore(setter, values))
        ch.tab, ch.team = self.tab, team
        self.backs.append((ch if ch.snaps else None, mine))
        return ch
