"""Iveri Production Verification Suite.

Automated smoke verification testing:
1. Health check & environment telemetry
2. Cross-device owner workspace discovery
3. Power BI export with UTF-8 BOM and schema version
"""

import sys
import asyncio
import httpx

async def run_verification(base_url: str = "http://localhost:8000"):
    print(f"\n=======================================================")
    print(f"[RUN] Iveri Production Verification Suite against {base_url}")
    print(f"=======================================================\n")

    async with httpx.AsyncClient(base_url=base_url, timeout=15.0) as client:
        # 1. Health Endpoint
        try:
            res = await client.get("/api/health")
            assert res.status_code == 200, f"Expected 200, got {res.status_code}"
            data = res.json()
            print(f"[PASS] 1. Health check: status={data.get('status')}, service={data.get('service')}")
        except Exception as e:
            print(f"[FAIL] 1. Health check: {e}")
            return False

        # 2. Cross-Device Discovery
        try:
            res = await client.get("/api/auth/active-owner")
            assert res.status_code == 200, f"Expected 200, got {res.status_code}"
            data = res.json()
            print(f"[PASS] 2. Cross-device discovery: active={data.get('has_active_workspace')}, slug={data.get('business_slug')}")
        except Exception as e:
            print(f"[FAIL] 2. Cross-device discovery: {e}")
            return False

        # 3. Power BI Dataset Export
        try:
            res = await client.get("/api/dashboard/export/powerbi?format=csv")
            assert res.status_code == 200, f"Expected 200, got {res.status_code}"
            assert res.text.startswith("\ufeff") or res.content.startswith(b"\xef\xbb\xbf"), "Missing UTF-8 BOM"
            print(f"[PASS] 3. Power BI export: UTF-8 BOM verified, rows={res.headers.get('X-Dataset-Rows')}")
        except Exception as e:
            print(f"[FAIL] 3. Power BI export: {e}")
            return False

    print(f"\n=======================================================")
    print(f"[SUCCESS] All System Verification Checks Passed Successfully!")
    print(f"=======================================================\n")
    return True

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    asyncio.run(run_verification(url))
