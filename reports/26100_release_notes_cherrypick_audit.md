# Cherry-pick audit for upstream/stabilization/26100

From-ref (previous release): `2605.0`  
To-ref (release branch): `upstream/stabilization/26100`

Each entry below is a cherry-pick container PR found on the release
branch for this cycle. A container that is *merged* keeps each
cherry-picked commit's original `(#NNNN)` subject, so the fix enters
the report under its own number and filtering the container out is
harmless. A container that is *squashed* carries only its own number,
and every fix it bundles would then be missing from the report
entirely. Catching that is why this sidecar exists.

The bundled PRs are extracted from the container's commit body (or,
for a container merged with a merge commit, from the commits it
merged in), then checked against what the report actually renders:

- ✓ present in the rendered report
- ⚠ collected but filtered OUT of the report (reason shown). These are
  the dangerous ones: confirm the filter is right before publishing.
- ○ already reported in a prior release, so correctly absent here
- ✗ neither in this report nor any prior one. Check whether it belongs
  to an earlier cycle before treating it as a loss.

Checking against the rendered output rather than the collected JSON is
deliberate: the latter reports a green tick for a fix the reader will
never see.


## o3de/o3de

- **#20091**: Cherrypick fixes to 26100 (first pass) _(merge commit: each picked commit keeps its own PR number)_
  - ✓ #19975: present in the rendered report
  - ✓ #19981: present in the rendered report
  - ✓ #19993: present in the rendered report
  - ✓ #20013: present in the rendered report
  - ✓ #20021: present in the rendered report
  - ✓ #20022: present in the rendered report
  - ✓ #20027: present in the rendered report
  - ✓ #20031: present in the rendered report
  - ✓ #20034: present in the rendered report
  - ✓ #20036: present in the rendered report
  - ✓ #20052: present in the rendered report
- **#20006**: (cherrypick) Replace Git-Based FetchContent Patching with patch-ng (#19998) _(merge commit: each picked commit keeps its own PR number)_
  - ✓ #19998: present in the rendered report
- **#19803**: Cherry pick release fixes from stabilization/26050 to development (#19803)
  - ✗ #19776: not in this report and not in any prior report; check whether it belongs to an earlier cycle
  - ✗ #19777: not in this report and not in any prior report; check whether it belongs to an earlier cycle
  - ✗ #19779: not in this report and not in any prior report; check whether it belongs to an earlier cycle
- **#19766**: Cherry-pick fixes from `stabilization/26050` to `development`  (#19766)
  - ○ #19727: already reported in a prior release (correctly absent here)
  - ○ #19739: already reported in a prior release (correctly absent here)
  - ○ #19757: already reported in a prior release (correctly absent here)
  - ○ #19758: already reported in a prior release (correctly absent here)
- **#19723**: (development) Cherry-pick fixes `stabilization/26050` --> `development` (#19723)
  - ○ #19635: already reported in a prior release (correctly absent here)
  - ○ #19647: already reported in a prior release (correctly absent here)
  - ○ #19701: already reported in a prior release (correctly absent here)
  - ○ #19703: already reported in a prior release (correctly absent here)
  - ○ #19706: already reported in a prior release (correctly absent here)
  - ○ #19712: already reported in a prior release (correctly absent here)
- **#19697**: Cherry pick fixes from `stabilization/26050` to `development` (#19697)
  - ○ #19665: already reported in a prior release (correctly absent here)
  - ○ #19673: already reported in a prior release (correctly absent here)
  - ○ #19692: already reported in a prior release (correctly absent here)
- **#19672**: Merge stabilization 26050 to dev 02 (#19672)
  - ○ #19033: already reported in a prior release (correctly absent here)
  - ○ #19261: already reported in a prior release (correctly absent here)
  - ○ #19588: already reported in a prior release (correctly absent here)
  - ○ #19589: already reported in a prior release (correctly absent here)
  - ○ #19592: already reported in a prior release (correctly absent here)
  - ○ #19596: already reported in a prior release (correctly absent here)
  - ○ #19608: already reported in a prior release (correctly absent here)
  - ○ #19611: already reported in a prior release (correctly absent here)
  - ○ #19624: already reported in a prior release (correctly absent here)
  - ○ #19632: already reported in a prior release (correctly absent here)
  - ○ #19634: already reported in a prior release (correctly absent here)
  - ○ #19635: already reported in a prior release (correctly absent here)
  - ○ #19637: already reported in a prior release (correctly absent here)
  - ○ #19639: already reported in a prior release (correctly absent here)
  - ○ #19646: already reported in a prior release (correctly absent here)
  - ○ #19647: already reported in a prior release (correctly absent here)
  - ○ #19651: already reported in a prior release (correctly absent here)
  - ○ #19655: already reported in a prior release (correctly absent here)
  - ○ #19658: already reported in a prior release (correctly absent here)
  - ○ #19660: already reported in a prior release (correctly absent here)
- **#19609**: Merge changes from Stabilization to development (#19609)
  - ○ #19588: already reported in a prior release (correctly absent here)
  - ○ #19589: already reported in a prior release (correctly absent here)
  - ○ #19592: already reported in a prior release (correctly absent here)
  - ○ #19608: already reported in a prior release (correctly absent here)
- **#19291**: Cherry pick more changes from QT6 branch (#19291)
  - _(no bundled PRs parsed from body)_
- **#19290**: Cherry-pick from `stabilization/25100` to `development` (splash screen and ciso646) (#19290)
  - ✗ #19275: not in this report and not in any prior report; check whether it belongs to an earlier cycle
  - ✗ #19286: not in this report and not in any prior report; check whether it belongs to an earlier cycle
- **#19282**: Cherry pick more changes from qt6 branch (#19282)
  - _(no bundled PRs parsed from body)_
- **#19277**: Cherry-pic `need-sync:to-development` changes from `stabilization` to `development` (#19277)
  - ✗ #19247: not in this report and not in any prior report; check whether it belongs to an earlier cycle
  - ✗ #19268: not in this report and not in any prior report; check whether it belongs to an earlier cycle
- **#19265**: Cherry-pick Lyshine cyclic inclusion fixes from QT6 branch (#19265)
  - _(no bundled PRs parsed from body)_
- **#19229**: Merge from stabilization25100 to development (1) (#19229)
  - ✗ #19183: not in this report and not in any prior report; check whether it belongs to an earlier cycle
  - ✗ #19184: not in this report and not in any prior report; check whether it belongs to an earlier cycle

## o3de/o3de-extras

- **#1054**: Sync changes from stabilization back to development _(merge commit: each picked commit keeps its own PR number)_
  - ○ #1050: already reported in a prior release (correctly absent here)

---

**Summary:** 15 container(s) checked, 59 bundled PR reference(s) parsed: 12 rendered, 0 filtered out, 38 already reported previously, 9 unaccounted for. **Action required before publishing.**
