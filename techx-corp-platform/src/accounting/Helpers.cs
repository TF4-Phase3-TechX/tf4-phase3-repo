// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

using System.Collections;

namespace Accounting
{
    internal static class Helpers
    {
        private static List<string> RelevantPrefixes = ["DOTNET_", "CORECLR_", "OTEL_", "KAFKA_"];

        public static IEnumerable<DictionaryEntry> FilterRelevant(this IDictionary envs)
        {
            foreach (DictionaryEntry env in envs)
            {
                foreach (var prefix in RelevantPrefixes)
                {
                    if (env.Key.ToString()?.StartsWith(prefix, StringComparison.InvariantCultureIgnoreCase) ?? false)
                    {
                        yield return env;
                    }
                }
            }
        }

        public static void OutputInOrder(this IEnumerable<DictionaryEntry> envs)
        {
            foreach (var env in envs.OrderBy(x => x.Key))
            {
                Console.WriteLine(FormatEnvironmentVariable(env));
            }
        }

        private static string FormatEnvironmentVariable(DictionaryEntry env)
        {
            var key = env.Key.ToString() ?? "";
            var value = IsSensitive(key) ? "<redacted>" : env.Value;
            return $"[{key}, {value}]";
        }

        private static bool IsSensitive(string key)
        {
            var sensitiveMarkers = new[] { "PASSWORD", "SECRET", "TOKEN", "KEY" };
            return sensitiveMarkers.Any(marker => key.Contains(marker, StringComparison.InvariantCultureIgnoreCase));
        }
    }
}
