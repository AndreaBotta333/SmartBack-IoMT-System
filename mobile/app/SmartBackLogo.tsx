import React from "react";
import { Image, StyleSheet } from "react-native";

export function SmartBackLogo({ large = false }: { large?: boolean }) {
  return (
    <Image
      accessibilityLabel="SmartBack"
      resizeMode="contain"
      source={require("./assets/smartback-logo-transparent.png")}
      style={large ? styles.large : styles.compact}
    />
  );
}

const styles = StyleSheet.create({
  large: { width: 286, height: 250 },
  compact: { width: 58, height: 58 },
});
